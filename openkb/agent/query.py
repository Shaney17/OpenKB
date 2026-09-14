"""Q&A agent for querying the OpenKB knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

from agents import Agent, Runner, ToolOutputImage, ToolOutputText, function_tool

from openkb.agent.tools import (
    artifact_event_from_write,
    get_wiki_page_content,
    is_tool_failure,
    read_wiki_file,
    read_wiki_image,
    write_kb_file,
)
from openkb.config import LlmCredentialBundle, normalize_litellm_model, resolve_model_settings
from openkb.schema import get_agents_md
from openkb.spaces import configured_spaces, is_project
from openkb.spaces import read_space_page as read_space_page_in
from openkb.spaces import search_spaces as search_spaces_in

MAX_TURNS = 50

_QUERY_INSTRUCTIONS_TEMPLATE = """\
You are OpenKB, a knowledge-base Q&A agent. You answer questions by searching the wiki.

{schema_md}

## Search strategy
1. Read index.md to see all documents and concepts with brief summaries.
   Each document is marked (short) or (pageindex) to indicate its type.
2. Read relevant summary pages (summaries/) for document overviews.
   Summaries may omit details — if you need more, follow the summary's
   `full_text` frontmatter field to the source (see step 4).
3. Read concept pages (concepts/) for cross-document synthesis.
4. For "who/what is X" questions about a specific named person, organization,
   place, or product, read the matching page in entities/ first.
5. When you need detailed source document content, each summary page has a
   `full_text` frontmatter field with the path to the original document content:
   - Short documents (doc_type: short): read_file with that path.
   - PageIndex documents (doc_type: pageindex): use get_page_content(doc_name, pages)
     with tight page ranges. The summary shows document tree structure with page
     ranges to help you target. Never fetch the whole document.
6. Source content may reference images. Short-doc .md pages link them
   note-relative (e.g. ![image](images/doc/file.png), resolved from
   wiki/sources/); long-doc JSON page metadata lists them wiki-root-relative
   (e.g. sources/images/doc/file.png). Pass either form as seen to the
   get_image tool — it accepts both.
7. Synthesize a clear, concise, well-cited answer grounded in wiki content.

Answer based only on wiki content. Be concise.
Before each tool call, output one short sentence explaining the reason.

If you cannot find relevant information, say so clearly.
"""

_SPACES_INSTRUCTIONS = """\

## This KB is a project — its content lives in spaces

This knowledge base is a *project container* synchronized from Confluence. Its
own index.md, concepts/ and summaries/ are EMPTY BY DESIGN: every compiled page
lives in a child space listed below. `read_file` cannot see those pages.

Spaces in this project: {space_list}

Override the search strategy above with this one:
1. Call `search_spaces(query)` FIRST, before `read_file`. Search with the
   user's own domain terms; retry with different terms before giving up.
2. Call `read_space_page(space, path)` on the most promising matches to read
   the full page — search returns short excerpts, never enough to answer from.
   Follow a page's `[[wikilinks]]` by reading them with `read_space_page` in
   the SAME space.
3. Use `list_spaces()` when you need to know which spaces exist, or when a
   search comes back empty across the board.
4. Cite pages as `<SPACE>/<path>` so the user can find them again.

Never tell the user this knowledge base is empty because index.md is empty —
that file is empty in every project. Search the spaces first.
"""


def build_query_agent(
    wiki_root: str,
    model: str,
    language: str = "en",
    bundle: "LlmCredentialBundle | None" = None,
    kb_dir: Path | None = None,
) -> Agent:
    """Build and return the Q&A agent.

    When *kb_dir* is a Confluence project (it has child space KBs under
    ``.openkb/spaces/``), the agent additionally gets the federated
    ``list_spaces`` / ``search_spaces`` / ``read_space_page`` tools and
    instructions that steer it to them. Without this the agent would read the
    project's deliberately-empty ``index.md`` and report that the KB has no
    content — the whole synchronized corpus sits one level down.
    """
    schema_md = get_agents_md(Path(wiki_root))
    instructions = _QUERY_INSTRUCTIONS_TEMPLATE.format(schema_md=schema_md)
    space_tools = _build_space_tools(kb_dir) if kb_dir is not None else []
    if kb_dir is not None and space_tools:
        instructions += _SPACES_INSTRUCTIONS.format(
            space_list=", ".join(sorted(configured_spaces(kb_dir))) or "(none)"
        )
    instructions += f"\n\nIMPORTANT: Answer in {language} language."

    @function_tool
    def read_file(path: str) -> str:
        """Read a Markdown file from the wiki.
        Args:
            path: File path relative to wiki root (e.g. 'summaries/paper.md').
        """
        return read_wiki_file(path, wiki_root)

    @function_tool
    def get_page_content(doc_name: str, pages: str) -> str:
        """Get text content of specific pages from a PageIndex (long) document.
        Only use for documents with doc_type: pageindex. For short documents,
        use read_file instead.
        Args:
            doc_name: Document name (e.g. 'attention-is-all-you-need').
            pages: Page specification (e.g. '3-5,7,10-12').
        """
        return get_wiki_page_content(doc_name, pages, wiki_root)

    @function_tool
    def get_image(image_path: str) -> ToolOutputImage | ToolOutputText:
        """View an image from the wiki.

        Use when a question asks about a specific figure, chart, or diagram
        you'd need to see to answer accurately.

        Args:
            image_path: Image path as it appears in the content — either
                wiki-root-relative ('sources/images/doc/p1_img1.png') or
                note-relative as used in sources/ .md pages
                ('images/doc/p1_img1.png').
        """
        result = read_wiki_image(image_path, wiki_root)
        if result["type"] == "image":
            return ToolOutputImage(image_url=result["image_url"])
        return ToolOutputText(text=result["text"])

    from agents.model_settings import ModelSettings

    if bundle is not None:
        model_settings = {
            "parallel_tool_calls": (
                bundle.parallel_tool_calls if bundle.parallel_tool_calls_explicit else False
            ),
            "extra_headers": bundle.extra_headers or None,
            "extra_args": {"timeout": bundle.timeout} if bundle.timeout is not None else None,
        }
    else:
        model_settings = resolve_model_settings()

    model = normalize_litellm_model(model, bundle.base_url if bundle is not None else None)
    return Agent(
        name="wiki-query",
        instructions=instructions,
        tools=[read_file, get_page_content, get_image, *space_tools],
        model=f"litellm/{model}",
        model_settings=ModelSettings(**model_settings),
    )


def _build_space_tools(kb_dir: Path) -> list:
    """Federated read tools for a Confluence project KB, or ``[]`` for a plain KB.

    All three return plain strings (never raise): a tool that raises aborts the
    run, whereas an in-band message lets the model correct a bad space name or
    path on its next turn. Failure strings use the prefixes
    ``openkb.agent.tools.is_tool_failure`` recognizes so the UI can render them
    as failed steps rather than confirmed reads.
    """
    if not is_project(kb_dir):
        return []
    spaces = sorted(configured_spaces(kb_dir))

    @function_tool
    def list_spaces() -> str:
        """List the Confluence spaces in this project and how much each holds.

        Call this when you need to know which spaces exist before searching, or
        when a search returned nothing anywhere.
        """
        return _format_space_list(kb_dir)

    @function_tool
    def search_spaces(query: str, spaces_filter: str = "", limit: int = 10) -> str:
        """Search compiled wiki pages across this project's spaces.

        This is the PRIMARY way to find content in a project KB. Returns ranked
        matches as ``<SPACE> <path> (tier, score)`` plus a short excerpt; read
        the promising ones in full with ``read_space_page``. ``compiled`` pages
        (concepts/entities/summaries) come first and are the ones to read;
        ``source`` pages are the raw ingested documents — large, so open one
        only when a compiled page lacks the detail you need.

        Args:
            query: Search terms — use the user's own domain vocabulary.
            spaces_filter: Optional comma-separated space keys to narrow the
                search (e.g. ``"PM,ENG"``). Empty searches every space.
            limit: Maximum number of matches to return (1-50).
        """
        selected = [part.strip() for part in spaces_filter.split(",") if part.strip()] or None
        try:
            matches = search_spaces_in(kb_dir, query, selected, max(1, min(limit, 50)))
        except ValueError as exc:
            return f"Unknown space: {exc}"
        if not matches:
            scope = spaces_filter or ", ".join(spaces)
            return (
                f"No matches for {query!r} in [{scope}]. "
                "Try different or broader terms, or call list_spaces()."
            )
        lines = []
        for hit in matches:
            lines.append(f"{hit['space']} {hit['path']} ({hit['tier']}, score {hit['score']})")
            lines.append(f"    {hit['excerpt']}")
        return "\n".join(lines)

    @function_tool
    def read_space_page(space: str, path: str) -> str:
        """Read one compiled wiki page in full from a project space.

        Args:
            space: Space key as shown by ``search_spaces`` / ``list_spaces``.
            path: Page path within that space's wiki, as returned by
                ``search_spaces`` (e.g. ``"concepts/order-execution.md"``).
        """
        try:
            return read_space_page_in(kb_dir, space, path)
        except ValueError as exc:
            return f"Unknown space: {exc}"
        except FileNotFoundError:
            return f"File not found: {space}/{path}"
        except OSError as exc:
            return f"Could not read {space}/{path}: {exc}"

    return [list_spaces, search_spaces, read_space_page]


def _format_space_list(kb_dir: Path) -> str:
    """Render the project's spaces with their sync status and compiled counts."""
    from openkb.confluence_projects import public_project

    try:
        items = public_project(kb_dir)["spaces"]
    except (ValueError, OSError) as exc:
        return f"Could not read the project's spaces: {exc}"
    if not items:
        return "This project has no Confluence spaces."
    lines = [f"{len(items)} space(s) in this project:"]
    for item in items:
        inventory = item.get("inventory") or {}
        counts = ", ".join(
            f"{len(inventory.get(kind) or [])} {kind}"
            for kind in ("documents", "concepts", "entities")
            if inventory.get(kind)
        )
        label = item.get("label") or item["key"]
        lines.append(f"- {item['key']} — {label} [{item.get('status', 'idle')}]")
        if counts:
            lines.append(f"    {counts}")
    lines.append("\nSearch them with search_spaces(query).")
    return "\n".join(lines)


def _resolve_tool_call_id(raw_item: Any) -> str | None:
    """Resolve a tool call's correlation id exactly as the Agents SDK's
    ``ToolCallItem.call_id`` / ``ToolCallOutputItem.call_id`` property does:
    prefer ``call_id``, fall back to ``id``, dict-aware.

    The ChatCompletions/LiteLLM path emits only ``id`` (no ``call_id``) on the
    output item, so without the ``id`` fallback the key written on the
    ``tool_call`` side and the key read on the ``tool_call_output_item`` side
    disagree, ``pending_calls.pop`` misses, and the ``output/*.html`` artifact
    card silently never fires. Deriving the key with this one helper on BOTH
    sides keeps them aligned.
    """
    if isinstance(raw_item, dict):
        return raw_item.get("call_id") or raw_item.get("id")
    return getattr(raw_item, "call_id", None) or getattr(raw_item, "id", None)


async def iter_agent_response_events(
    agent: Agent,
    input_data: str | list[dict[str, Any]],
    *,
    max_turns: int = MAX_TURNS,
    run_config: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield non-TTY events for a streamed agent response.

    The CLI renders these events to stdout; the REST API serializes the same
    events as SSE. Events: ``{"event": "delta", "data": {"text": ...}}`` for
    each response-text delta, ``{"event": "tool_call", "data": {...}}`` for
    tool invocations, ``{"event": "tool_result", "data": {"name",
    "arguments", "ok"}}`` when each one returns, and a final ``{"event":
    "final", "data": {"answer": ..., "history": [...]}}`` carrying the complete
    answer and reusable Agents SDK history.

    ``tool_result.ok`` is False when the tool returned one of its in-band
    failure strings (see ``openkb.agent.tools.is_tool_failure``). Read tools
    report a missing path by RETURNING a message rather than raising, so the
    SDK sees every call succeed; without this event a read that found nothing
    is indistinguishable from one that delivered content, and the UI paints a
    confirmed-read check on both.
    """
    from agents import RawResponsesStreamEvent, RunItemStreamEvent
    from openai.types.responses import ResponseTextDeltaEvent

    result = (
        Runner.run_streamed(agent, input_data, max_turns=max_turns, run_config=run_config)
        if run_config
        else Runner.run_streamed(agent, input_data, max_turns=max_turns)
    )
    collected: list[str] = []
    pending_calls: dict[str, tuple[str, str]] = {}

    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            if isinstance(event.data, ResponseTextDeltaEvent):
                text = event.data.delta
                if text:
                    collected.append(text)
                    yield {"event": "delta", "data": {"text": text}}
        elif isinstance(event, RunItemStreamEvent):
            item = event.item
            if item.type == "tool_call_item":
                raw_item = item.raw_item
                name = getattr(raw_item, "name", "?")
                arguments = getattr(raw_item, "arguments", "") or ""
                call_id = _resolve_tool_call_id(raw_item)
                if call_id:
                    pending_calls[call_id] = (name, arguments)
                yield {"event": "tool_call", "data": {"name": name, "arguments": arguments}}
            elif item.type == "tool_call_output_item":
                raw_item = item.raw_item
                call_id = _resolve_tool_call_id(raw_item)
                name, arguments = (
                    pending_calls.pop(call_id, ("", "")) if isinstance(call_id, str) else ("", "")
                )
                output = str(getattr(item, "output", "") or "")
                if name:
                    yield {
                        "event": "tool_result",
                        "data": {
                            "name": name,
                            "arguments": arguments,
                            "ok": not is_tool_failure(output),
                        },
                    }
                payload = artifact_event_from_write(name, arguments, output)
                if payload is not None:
                    yield {"event": "artifact", "data": payload}

    answer = "".join(collected).strip()
    if not answer:
        answer = (result.final_output or "").strip()
    yield {
        "event": "final",
        "data": {
            "answer": answer,
            "history": result.to_input_list(),
        },
    }


def build_chat_agent(
    kb_dir: Path,
    model: str,
    language: str = "en",
    bundle: "LlmCredentialBundle | None" = None,
) -> Agent:
    """Build the chat agent: query agent + a write tool restricted to
    ``<kb>/wiki/explorations/**`` and ``<kb>/output/**`` + a ``ShellTool``
    advertising locally-installed Anthropic-style skills.

    This is the variant used by the interactive ``openkb chat`` REPL so users
    can iterate on generated artifacts (e.g. ``output/skills/<name>/``) via
    natural-language follow-ups without giving the agent unrestricted write
    access to the wiki.

    Skill discovery: ``openkb/agent/skills.scan_local_skills`` looks ONLY at
    the skills bundled with OpenKB — it does not sweep the machine for skills
    installed for other tools, which would let unrelated instructions steer a
    KB's answers. Any found skill is exposed to the agent via
    ``ShellTool.environment.skills`` so the model can ``cat`` the skill body
    and follow its instructions when the user's request matches.
    """
    wiki_root = str(kb_dir / "wiki")
    kb_root = str(kb_dir)
    base = build_query_agent(wiki_root, model, language=language, bundle=bundle, kb_dir=kb_dir)

    @function_tool
    def write_file(path: str, content: str) -> str:
        """Write a text file under the KB.

        Allowed paths (relative to KB root):
          * ``wiki/explorations/**`` — chat-derived notes.
          * ``output/**``            — generator artifacts (skills, etc.).

        Any other path is rejected. Parent directories are created.

        Args:
            path: File path relative to KB root
                (e.g. ``"output/skills/demo/SKILL.md"``).
            content: Full text content to write (overwrites if file exists).
        """
        return write_kb_file(path, content, kb_root)

    extra_tools: list = [write_file]
    skill_instructions_addendum = ""

    # Skill discovery via function tools. The agents SDK has a richer
    # ``ShellTool``+``ShellToolLocalSkill`` mechanism for this, but those
    # are OpenAI Responses-API hosted tools; LiteLLM routes through
    # ChatCompletions which rejects hosted tools. So we use plain
    # ``function_tool`` primitives that work with any LiteLLM-routed model.
    from openkb.agent.skills import scan_local_skills

    skills = scan_local_skills(kb_dir)
    skill_index = {s["name"]: s for s in skills}

    if skill_index:
        skill_list_text = _format_skill_list(skills)

        @function_tool
        def list_skills() -> str:
            """List skills available in this environment.

            Returns a text catalog of installed Anthropic-style skills.
            Each entry has a name and a one-line description; use the
            description to decide whether the skill matches the user's
            request, then call ``read_skill(name)`` to load its body.
            """
            return skill_list_text

        @function_tool
        def read_skill(name: str) -> str:
            """Read a skill's ``SKILL.md`` body.

            Call this once you've decided a skill matches the user's
            request. The returned text is the full skill instructions
            (frontmatter stripped). Follow it as your working method
            and write outputs via the ``write_file`` tool.

            Args:
                name: skill name as listed by ``list_skills``.
            """
            entry = skill_index.get(name)
            if entry is None:
                return f"Unknown skill: {name!r}. Call list_skills() to see available skills."
            md_path = Path(entry["path"]) / "SKILL.md"
            try:
                text = md_path.read_text(encoding="utf-8")
            except OSError as exc:
                return f"Could not read {md_path}: {exc}"
            # Strip frontmatter, return body only.
            from openkb.agent.skills import _parse_frontmatter

            _, body = _parse_frontmatter(text)
            return body

        @function_tool
        def read_skill_file(name: str, path: str) -> str:
            """Read a supporting file from inside a skill's directory.

            Skills are written progressive-disclosure style: ``SKILL.md`` is a
            thin router that names deeper files (``references/**``,
            playbooks, format specs) to load only when they apply. Use this to
            open one once ``SKILL.md`` tells you to — ``read_file`` cannot,
            it reads the wiki, not the skill.

            Args:
                name: skill name as listed by ``list_skills``.
                path: file path relative to the skill directory
                    (e.g. ``"references/lanes/02-process.md"``).
            """
            entry = skill_index.get(name)
            if entry is None:
                return f"Unknown skill: {name!r}. Call list_skills() to see available skills."
            from openkb.agent.skills import read_skill_support_file

            return read_skill_support_file(Path(entry["path"]), path)

        extra_tools.extend([list_skills, read_skill, read_skill_file])

        # Build the prompt addendum listing skill names + descriptions
        # right inside the system prompt so the model sees them up front
        # and knows what to look for, even before deciding to call
        # list_skills(). This is the difference between "agent
        # eventually discovers skills" and "agent treats skill use as
        # the default for matching requests".
        skill_lines = []
        for s in skills:
            desc_one_line = " ".join(s["description"].split())
            skill_lines.append(f"- **{s['name']}** — {desc_one_line}")
        skill_instructions_addendum = (
            "\n\n## Available skills\n\n"
            "The following Anthropic-style skill packages are installed in "
            "this environment. **When a user request matches a skill's "
            "description (e.g. 'make a deck', 'generate slides', 'draft a "
            "report'), you MUST call `read_skill(name)` to load that "
            "skill's full instructions and follow them strictly** — do not "
            "freestyle the output format if a skill covers it. When a "
            "skill's body points at one of its own supporting files, open it "
            "with `read_skill_file(name, path)` — `read_file` reads the "
            "wiki and will not find it.\n\n"
            + "\n".join(skill_lines)
            + "\n\nIf no listed skill matches the request, proceed with "
            "your default tools."
        )

    new_instructions = (base.instructions or "") + skill_instructions_addendum
    return base.clone(
        tools=[*base.tools, *extra_tools],
        instructions=new_instructions,
    )


def _format_skill_list(skills: list[dict[str, str]]) -> str:
    """Render the skill catalog as a compact text block for the agent."""
    if not skills:
        return "No skills installed."
    lines = [f"{len(skills)} skill(s) available:\n"]
    for s in skills:
        lines.append(f"- {s['name']}")
        # Indent description; keep it one paragraph so the agent reads it fast.
        desc = " ".join(s["description"].split())
        lines.append(f"    {desc}")
    lines.append("\nTo use a skill, call read_skill(name) and follow its instructions.")
    return "\n".join(lines)


async def run_query(
    question: str,
    kb_dir: Path,
    model: str,
    stream: bool = False,
    *,
    raw: bool = False,
    run_config: Any = None,
    bundle: LlmCredentialBundle | None = None,
) -> str:
    """Run a Q&A query against the knowledge base.

    Args:
        question: The user's question.
        kb_dir: Root of the knowledge base.
        model: LLM model name.
        stream: If True, print response tokens to stdout as they arrive.
        raw: If True, write raw markdown source instead of rendering it
            (still keeps tool-call line styling).

    Returns:
        The agent's final answer as a string.
    """
    import sys

    from agents import RawResponsesStreamEvent, RunItemStreamEvent
    from openai.types.responses import ResponseTextDeltaEvent

    from openkb.config import resolve_effective_config

    config = resolve_effective_config(kb_dir)[0]
    language: str = config.get("language", "en")

    wiki_root = str(kb_dir / "wiki")

    agent = build_query_agent(wiki_root, model, language=language, bundle=bundle, kb_dir=kb_dir)

    if not stream:
        result = (
            await Runner.run(agent, question, max_turns=MAX_TURNS, run_config=run_config)
            if run_config
            else await Runner.run(agent, question, max_turns=MAX_TURNS)
        )
        return result.final_output or ""

    import os

    use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR", "")

    from openkb.agent.chat import (
        _build_style,
        _fmt,
        _format_tool_line,
        _make_markdown,
        _make_rich_console,
    )

    style = _build_style(use_color)

    from rich.live import Live

    if use_color and not raw:
        console = _make_rich_console()
    else:
        console = None  # type: ignore[assignment]

    def _start_live() -> Live | None:
        if console is None:
            return None
        lv = Live(console=console, vertical_overflow="visible")
        lv.start()
        return lv

    live: Live | None = None
    last_was_text = False
    need_blank_before_text = False
    result = (
        Runner.run_streamed(agent, question, max_turns=MAX_TURNS, run_config=run_config)
        if run_config
        else Runner.run_streamed(agent, question, max_turns=MAX_TURNS)
    )
    collected: list[str] = []
    segment: list[str] = []
    try:
        live = _start_live()
        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                if isinstance(event.data, ResponseTextDeltaEvent):
                    text = event.data.delta
                    if text:
                        if need_blank_before_text:
                            if console is not None:
                                print()
                                segment = []
                                live = _start_live()
                            else:
                                sys.stdout.write("\n")
                            need_blank_before_text = False
                        collected.append(text)
                        segment.append(text)
                        last_was_text = True
                        if live:
                            if "\n" in text:
                                joined = "".join(segment)
                                visible = joined[: joined.rfind("\n") + 1]
                                if visible:
                                    live.update(_make_markdown(visible))
                        else:
                            sys.stdout.write(text)
                            sys.stdout.flush()
            elif isinstance(event, RunItemStreamEvent):
                item = event.item
                if item.type == "tool_call_item":
                    if last_was_text:
                        if live:
                            if segment:
                                live.update(_make_markdown("".join(segment)))
                            live.stop()
                            live = None
                        else:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                        last_was_text = False
                    raw_item = item.raw_item
                    name = getattr(raw_item, "name", "?")
                    args = getattr(raw_item, "arguments", "") or ""
                    if live:
                        live.stop()
                        live = None
                    _fmt(style, ("class:tool", _format_tool_line(name, args) + "\n"))
                    need_blank_before_text = True
                elif item.type == "tool_call_output_item":
                    pass
    finally:
        if live:
            if segment:
                live.update(_make_markdown("".join(segment)))
            live.stop()
        print()
    return "".join(collected) if collected else result.final_output or ""


def build_run_config_from_bundle(model: str, bundle: "LlmCredentialBundle | None") -> Any:
    """Build an Agents-SDK `RunConfig` from a credential bundle.

    When *bundle* is `None` (CLI path), returns `None` so the runner falls
    back to the default provider (process-wide `litellm.api_key` / env vars).
    When a bundle is supplied, a dedicated `LitellmModel` instance is created
    with the per-KB `api_key` and `base_url` so concurrent requests on the
    shared event-loop thread never read each other's credentials.

    The model passed to `LitellmModel` is a LiteLLM provider/model string. The
    ``litellm/`` Agent-layer prefix must NOT be added here. For an explicitly
    configured OpenAI-compatible base URL, an otherwise unqualified private
    model name is normalized to ``openai/<model>``.
    """
    if bundle is None:
        return None
    from agents import RunConfig
    from agents.extensions.models.litellm_model import LitellmModel

    litellm_model = LitellmModel(
        model=normalize_litellm_model(model, bundle.base_url),
        base_url=bundle.base_url,
        api_key=bundle.api_key,
    )
    return RunConfig(model=litellm_model)
