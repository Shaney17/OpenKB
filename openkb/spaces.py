"""Read-side federation across a project's Confluence child space KBs.

A Confluence-backed *project* KB is a container: ``openkb/confluence.py`` never
writes into the project's own ``wiki/``, it compiles each space into a child KB
under ``<project>/.openkb/spaces/<slug>/``. Everything that READS a project
therefore has to fan out across those children, or it sees the project's empty
``index.md`` and concludes the KB has no content.

This module is the single place that fan-out lives. It is deliberately free of
Click and FastAPI so both the MCP facade (``api_mcp_router``) and the in-process
Q&A agent (``agent/query``) can share one implementation instead of each growing
its own. ``openkb.confluence_projects`` is imported lazily for the same reason
``openkb.confluence`` does it: that module imports ``openkb.cli`` at module
scope, and dragging the whole CLI into the agent import path would be both slow
and cycle-prone.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SKIP_PAGES = {"AGENTS.md", "log.md"}

#: Pages under ``wiki/sources/`` are the raw ingested documents; everything else
#: (concepts/, entities/, summaries/, reports/) is compiled knowledge. Raw
#: sources repeat a term far more often than the page that distils it, so pure
#: term-frequency buries the distilled page under a 40k-character dump of its
#: own input. Ranking compiled pages first mirrors the KB's documented search
#: strategy (summaries/concepts first, source text only when detail is needed)
#: and keeps a reader from spending its whole context on one raw document.
_RAW_TIER = "sources"


def _projects():
    from openkb import confluence_projects

    return confluence_projects


def configured_spaces(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Return the project's space map (``{ref: entry}``), empty when not a project."""
    try:
        return dict(_projects().load_project(project_dir)["spaces"])
    except (ValueError, OSError):
        # A corrupt/unreadable project file must degrade to "no spaces" for the
        # read path, not break an unrelated query.
        return {}


def is_project(project_dir: Path) -> bool:
    """True when this KB federates content from at least one child space KB."""
    return bool(configured_spaces(project_dir))


def space_dir(project_dir: Path, key: str) -> Path:
    """Resolve a space reference to its child KB root.

    Accepts the configured ref, the canonical Confluence key, or the numeric
    Confluence id — all case-insensitively, since an agent (or a user) will
    reach for whichever of the three it last saw.
    """
    configured = configured_spaces(project_dir)
    canonical = key.strip().upper()
    ref = canonical
    if ref not in configured:
        ref = next(
            (
                candidate
                for candidate, entry in configured.items()
                if canonical
                in {
                    str(entry.get("key") or "").upper(),
                    str(entry.get("confluence_id") or "").upper(),
                }
            ),
            "",
        )
    if not ref:
        raise ValueError(f"Space {canonical!r} is not assigned to this project")
    return _projects().child_kb_dir(project_dir, ref)


#: Wiki folders whose entries a project's federated inventory merges. Each
#: merged name is qualified as ``<SPACE>/<name>`` so it stays unique across
#: spaces AND round-trips back to its child KB through ``resolve_page`` — the
#: web UI builds a page path as ``<type>/<name>`` and needs no extra plumbing.
_MERGED_SECTIONS = ("summaries", "concepts", "entities", "reports")


def qualify(space: str, name: str) -> str:
    return f"{space}/{name}"


def project_inventory(project_dir: Path) -> dict[str, Any]:
    """Merge every child space KB's inventory into one project-level view.

    A project KB's own ``hashes.json`` and ``wiki/`` are empty by design, so
    ``get_kb_list`` on it reports a knowledge base with nothing in it — which
    is what the sidebar count and the KB detail page were showing even though
    the sync had compiled hundreds of pages one level down.
    """
    from openkb.cli import get_kb_list

    merged: dict[str, Any] = {"documents": [], "document_count": 0}
    for section in _MERGED_SECTIONS:
        merged[section] = []
    for key in sorted(configured_spaces(project_dir)):
        child = space_dir(project_dir, key)
        if not (child / ".openkb").is_dir():
            continue
        inventory = get_kb_list(child)
        for document in inventory.get("documents", []):
            merged["documents"].append({**document, "space": key})
        for section in _MERGED_SECTIONS:
            merged[section].extend(qualify(key, name) for name in inventory.get(section, []))
    merged["document_count"] = len(merged["documents"])
    return merged


def kb_inventory(kb_dir: Path) -> dict[str, Any]:
    """Inventory for ``/api/v1/list``: federated for a project, plain otherwise."""
    from openkb.cli import get_kb_list

    return project_inventory(kb_dir) if is_project(kb_dir) else get_kb_list(kb_dir)


def resolve_page(project_dir: Path, path: str) -> tuple[Path, str]:
    """Map a project-level wiki path to the (child KB, path-within-its-wiki).

    Accepts the ``<type>/<SPACE>/<name>`` form that ``project_inventory``
    produces and the ``<SPACE>/<type>/<name>`` form emitted by query agents.
    Unknown spaces and other paths resolve against the project's own wiki.
    """
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in _MERGED_SECTIONS:
        try:
            child = space_dir(project_dir, parts[1])
        except ValueError:
            return project_dir, path
        return child, "/".join([parts[0], *parts[2:]])
    if len(parts) >= 3 and parts[1] in (*_MERGED_SECTIONS, "sources"):
        try:
            child = space_dir(project_dir, parts[0])
        except ValueError:
            return project_dir, path
        return child, "/".join(parts[1:])
    return project_dir, path


def project_index(project_dir: Path) -> str:
    """Render the roll-up ``index.md`` a project KB has no real file for.

    The project's own ``wiki/index.md`` is the empty scaffold every project
    starts with; showing it verbatim is what made a fully-synced KB look
    broken. This lists what each space actually holds instead.
    """
    from openkb.confluence_projects import public_project

    lines = ["# Project index", ""]
    try:
        items = public_project(project_dir)["spaces"]
    except (ValueError, OSError) as exc:
        return f"{lines[0]}\n\nCould not read this project's spaces: {exc}\n"
    if not items:
        return "# Project index\n\nThis project has no Confluence spaces yet.\n"
    lines.append(
        "This knowledge base is a Confluence project: its pages live in the "
        "spaces below, not in the project's own wiki."
    )
    lines.append("")
    for item in items:
        key = str(item["key"])
        inventory = item.get("inventory") or {}
        lines.append(f"## {item.get('label') or key} (`{key}`)")
        lines.append("")
        lines.append(f"- Status: {item.get('status', 'idle')}")
        lines.append(f"- Documents: {inventory.get('document_count', 0)}")
        for section in _MERGED_SECTIONS:
            entries = inventory.get(section) or []
            if entries:
                lines.append(f"- {section.capitalize()}: {len(entries)}")
        lines.append("")
    return "\n".join(lines)


def read_space_page(project_dir: Path, space: str, path: str) -> str:
    """Read one compiled Markdown page out of a child space KB."""
    root = space_dir(project_dir, space)
    rel = path if path.endswith(".md") else f"{path}.md"
    wiki = (root / "wiki").resolve()
    target = (wiki / rel).resolve()
    if not target.is_relative_to(wiki):
        raise ValueError("Invalid wiki page path")
    if not target.is_file():
        raise FileNotFoundError(path)
    return target.read_text(encoding="utf-8")


def search_spaces(
    project_dir: Path,
    query: str,
    spaces: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Keyword-score compiled wiki pages across all or selected child spaces.

    Scoring is deliberately plain term-frequency over the page text: the KB's
    own semantics live in the compiled concept/entity pages, so a cheap literal
    scan over them is enough to hand the agent a shortlist to read properly.

    Results are tiered before they are scored — compiled pages first, raw
    ``sources/`` second (see ``_RAW_TIER``) — so a distilled concept page is
    never buried under the raw document it was distilled from. Each hit carries
    its ``tier`` so callers can label it.
    """
    words = {w.casefold() for w in re.findall(r"[\w-]+", query) if len(w) > 1}
    if not words:
        return []
    configured = list(configured_spaces(project_dir))
    selected = [key.strip().upper() for key in spaces] if spaces else configured
    hits: list[dict[str, Any]] = []
    for key in selected:
        root = space_dir(project_dir, key)
        wiki = root / "wiki"
        if not wiki.is_dir():
            continue
        for path in wiki.rglob("*.md"):
            if path.name in _SKIP_PAGES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            folded = text.casefold()
            score = sum(folded.count(word) for word in words)
            if not score:
                continue
            first = min((folded.find(word) for word in words if word in folded), default=0)
            start = max(0, first - 160)
            excerpt = re.sub(r"\s+", " ", text[start : start + 520]).strip()
            rel = path.relative_to(wiki).as_posix()
            hits.append(
                {
                    "space": key,
                    "path": rel,
                    "score": score,
                    "tier": "source" if rel.split("/", 1)[0] == _RAW_TIER else "compiled",
                    "excerpt": excerpt,
                }
            )
    ranked = sorted(
        hits,
        key=lambda item: (item["tier"] == "source", -item["score"], item["space"], item["path"]),
    )
    # A fixed top-N with all compiled pages first could consume every slot:
    # the agent then sees only summaries/concepts even though a matching full
    # Confluence page exists under sources/. Reserve some slots for originals.
    if limit >= 2:
        compiled = [hit for hit in ranked if hit["tier"] != "source"]
        sources = [hit for hit in ranked if hit["tier"] == "source"]
        if compiled and sources:
            source_slots = min(len(sources), max(1, limit // 3))
            compiled_hits = compiled[: limit - source_slots]
            source_hits = sources[: limit - len(compiled_hits)]
            return [*compiled_hits, *source_hits]
    return ranked[:limit]
