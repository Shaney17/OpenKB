"""Tests for read-side federation across a project's Confluence child space KBs.

The bug these lock down: a Confluence project KB's own ``wiki/`` is empty by
design (every page is compiled into a child KB under ``.openkb/spaces/``), so a
query agent bound only to the project's wiki read an empty ``index.md`` and told
the user the knowledge base had no content.
"""

from __future__ import annotations

import json

import pytest

from openkb.agent.query import build_query_agent
from openkb.agent.tools import is_tool_failure
from openkb.spaces import (
    configured_spaces,
    is_project,
    project_index,
    project_inventory,
    read_space_page,
    resolve_page,
    search_spaces,
    space_dir,
)


def _plain_kb(root):
    """A normal (non-project) KB: .openkb + wiki, no Confluence spaces."""
    (root / ".openkb").mkdir(parents=True)
    (root / "wiki").mkdir(parents=True)
    (root / ".openkb" / "hashes.json").write_text("{}", encoding="utf-8")
    return root


def _project_kb(root, spaces: dict[str, dict[str, str]]):
    """A project KB whose child space KBs hold the given ``{page: text}`` maps."""
    _plain_kb(root)
    entries = {}
    for key, pages in spaces.items():
        child = root / ".openkb" / "spaces" / key.lower()
        wiki = child / "wiki"
        (child / ".openkb").mkdir(parents=True)
        wiki.mkdir(parents=True)
        for rel, text in pages.items():
            target = wiki / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        entries[key] = {
            "ref": key,
            "key": key,
            "confluence_id": f"{1000 + len(entries)}",
            "label": f"{key} space",
            "status": "succeeded",
        }
    (root / ".openkb" / "confluence-project.json").write_text(
        json.dumps({"version": 1, "connection": {}, "spaces": entries}),
        encoding="utf-8",
    )
    return root


class TestProjectDetection:
    def test_plain_kb_is_not_a_project(self, tmp_path):
        kb = _plain_kb(tmp_path / "kb")
        assert is_project(kb) is False
        assert configured_spaces(kb) == {}

    def test_project_kb_lists_its_spaces(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"index.md": "# x"}, "ENG": {}})
        assert is_project(kb) is True
        assert set(configured_spaces(kb)) == {"PM", "ENG"}

    def test_corrupt_project_file_degrades_to_no_spaces(self, tmp_path):
        """A read must not explode on a malformed project file — it degrades."""
        kb = _plain_kb(tmp_path / "kb")
        (kb / ".openkb" / "confluence-project.json").write_text("{not json", encoding="utf-8")
        assert configured_spaces(kb) == {}
        assert is_project(kb) is False


class TestSpaceDir:
    def test_resolves_by_ref_case_insensitively(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert space_dir(kb, "pm") == kb / ".openkb" / "spaces" / "pm"

    def test_resolves_by_confluence_id(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert space_dir(kb, "1000") == kb / ".openkb" / "spaces" / "pm"

    def test_unassigned_space_raises(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        with pytest.raises(ValueError, match="not assigned"):
            space_dir(kb, "NOPE")


class TestSearchSpaces:
    def test_finds_pages_across_spaces_and_ranks_by_frequency(self, tmp_path):
        kb = _project_kb(
            tmp_path / "kb",
            {
                "PM": {
                    "concepts/orderbook.md": "sổ lệnh sổ lệnh sổ lệnh hiển thị",
                    "concepts/fees.md": "phí giao dịch",
                },
                "ENG": {"concepts/api.md": "sổ lệnh API"},
            },
        )
        hits = search_spaces(kb, "sổ lệnh")
        paths = [(h["space"], h["path"]) for h in hits]
        assert ("PM", "concepts/orderbook.md") in paths
        assert ("ENG", "concepts/api.md") in paths
        assert ("PM", "concepts/fees.md") not in paths
        # Highest term frequency ranks first.
        assert paths[0] == ("PM", "concepts/orderbook.md")

    def test_space_filter_narrows_the_search(self, tmp_path):
        kb = _project_kb(
            tmp_path / "kb",
            {"PM": {"a.md": "orderbook"}, "ENG": {"b.md": "orderbook"}},
        )
        hits = search_spaces(kb, "orderbook", ["PM"])
        assert {h["space"] for h in hits} == {"PM"}

    def test_skips_agents_and_log_pages(self, tmp_path):
        """AGENTS.md/log.md are scaffolding, never answers — they must not rank."""
        kb = _project_kb(
            tmp_path / "kb",
            {"PM": {"AGENTS.md": "orderbook", "log.md": "orderbook", "c.md": "orderbook"}},
        )
        assert [h["path"] for h in search_spaces(kb, "orderbook")] == ["c.md"]

    def test_limit_caps_results(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {f"p{i}.md": "orderbook" for i in range(10)}})
        assert len(search_spaces(kb, "orderbook", None, 3)) == 3

    def test_blank_query_returns_nothing(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"a.md": "orderbook"}})
        assert search_spaces(kb, "   ") == []


class TestReadSpacePage:
    def test_reads_a_page_with_and_without_md_suffix(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/x.md": "body"}})
        assert read_space_page(kb, "PM", "concepts/x.md") == "body"
        assert read_space_page(kb, "PM", "concepts/x") == "body"

    def test_missing_page_raises_file_not_found(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        with pytest.raises(FileNotFoundError):
            read_space_page(kb, "PM", "nope.md")

    def test_traversal_out_of_the_space_wiki_is_rejected(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        (kb / ".openkb" / "spaces" / "pm" / "secret.md").write_text("s", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid wiki page path"):
            read_space_page(kb, "PM", "../secret.md")


class TestQueryAgentFederation:
    def test_plain_kb_has_original_quote_tool_without_federated_tools(self, tmp_path):
        kb = _plain_kb(tmp_path / "kb")
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        assert {t.name for t in agent.tools} == {
            "read_file",
            "get_page_content",
            "get_image",
            "quote_source",
        }

    def test_no_kb_dir_keeps_base_tools(self, tmp_path):
        """The kwarg is optional — callers that don't pass it are unaffected."""
        agent = build_query_agent(str(tmp_path), "gpt-4o-mini")
        assert len(agent.tools) == 4

    def test_project_kb_gains_the_federated_tools(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"a.md": "x"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        names = {t.name for t in agent.tools}
        assert {"list_spaces", "search_spaces", "read_space_page"} <= names

    def test_project_instructions_steer_away_from_the_empty_index(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"a.md": "x"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        assert "search_spaces(query)" in agent.instructions
        assert "PM" in agent.instructions
        # The specific failure mode this replaced: reporting an empty KB.
        assert "empty because index.md is empty" in agent.instructions

    def test_plain_kb_instructions_do_not_mention_spaces(self, tmp_path):
        kb = _plain_kb(tmp_path / "kb")
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        assert "search_spaces" not in agent.instructions


class TestFederatedToolFailuresAreInBand:
    """The tools must RETURN failures (a raise aborts the whole run) and use a
    prefix ``is_tool_failure`` recognizes, so the UI can render a failed step."""

    def _tool(self, agent, name):
        return next(t for t in agent.tools if t.name == name)

    @staticmethod
    def _ctx():
        """A minimal ToolContext — the SDK dereferences it on the error path."""
        from agents.tool_context import ToolContext

        return ToolContext(context=None, tool_name="t", tool_call_id="c", tool_arguments="{}")

    @pytest.mark.asyncio
    async def test_read_space_page_reports_unknown_space_in_band(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"a.md": "x"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "read_space_page")
        out = await tool.on_invoke_tool(self._ctx(), json.dumps({"space": "NOPE", "path": "a.md"}))
        assert out.startswith("Unknown space:")
        assert is_tool_failure(out)

    @pytest.mark.asyncio
    async def test_read_space_page_reports_missing_page_in_band(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "read_space_page")
        out = await tool.on_invoke_tool(self._ctx(), json.dumps({"space": "PM", "path": "gone.md"}))
        assert is_tool_failure(out)

    @pytest.mark.asyncio
    async def test_read_space_page_returns_content(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/x.md": "the body"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "read_space_page")
        out = await tool.on_invoke_tool(
            self._ctx(), json.dumps({"space": "PM", "path": "concepts/x.md"})
        )
        assert out == "the body"
        assert not is_tool_failure(out)

    @pytest.mark.asyncio
    async def test_search_reports_hits_with_space_and_path(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/x.md": "orderbook detail"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "search_spaces")
        out = await tool.on_invoke_tool(self._ctx(), json.dumps({"query": "orderbook"}))
        assert "PM concepts/x.md" in out
        assert not is_tool_failure(out)

    @pytest.mark.asyncio
    async def test_empty_search_is_not_a_failure(self, tmp_path):
        """Finding nothing is a true result, not a broken tool — the step stays
        green and the message tells the model to retry with other terms."""
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/x.md": "orderbook"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "search_spaces")
        out = await tool.on_invoke_tool(self._ctx(), json.dumps({"query": "zzzznothing"}))
        assert "No matches" in out
        assert not is_tool_failure(out)

    @pytest.mark.asyncio
    async def test_list_spaces_names_each_space_and_status(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/x.md": "x"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        tool = self._tool(agent, "list_spaces")
        out = await tool.on_invoke_tool(self._ctx(), "{}")
        assert "PM" in out
        assert "succeeded" in out


class TestSearchRanking:
    def test_compiled_pages_outrank_raw_sources(self, tmp_path):
        """A raw source repeats a term far more than the concept distilled from
        it; without tiering, the 40k-char dump buries its own summary."""
        kb = _project_kb(
            tmp_path / "kb",
            {
                "PM": {
                    "sources/big.md": "orderbook " * 500,
                    "concepts/orderbook.md": "orderbook",
                }
            },
        )
        hits = search_spaces(kb, "orderbook")
        assert [h["path"] for h in hits] == ["concepts/orderbook.md", "sources/big.md"]
        assert [h["tier"] for h in hits] == ["compiled", "source"]

    def test_score_still_orders_within_a_tier(self, tmp_path):
        kb = _project_kb(
            tmp_path / "kb",
            {"PM": {"concepts/a.md": "orderbook", "concepts/b.md": "orderbook orderbook"}},
        )
        assert [h["path"] for h in search_spaces(kb, "orderbook")] == [
            "concepts/b.md",
            "concepts/a.md",
        ]

    def test_raw_sources_are_still_returned(self, tmp_path):
        """Tiering demotes raw sources, it must not hide them — they hold the
        detail a compiled page omits."""
        kb = _project_kb(tmp_path / "kb", {"PM": {"sources/big.md": "orderbook"}})
        hits = search_spaces(kb, "orderbook")
        assert [h["path"] for h in hits] == ["sources/big.md"]

    def test_source_survives_when_compiled_pages_fill_the_limit(self, tmp_path):
        pages = {f"concepts/c{i}.md": "orderbook" for i in range(12)}
        pages["sources/original.md"] = "orderbook full Confluence document"
        kb = _project_kb(tmp_path / "kb", {"PM": pages})
        hits = search_spaces(kb, "orderbook", limit=6)
        assert len(hits) == 6
        assert hits[0]["tier"] == "compiled"
        assert any(hit["path"] == "sources/original.md" for hit in hits)

    def test_project_instructions_require_source_verification(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"sources/original.md": "detail"}})
        agent = build_query_agent(str(kb / "wiki"), "gpt-4o-mini", kb_dir=kb)
        assert "ORIGINAL full" in agent.instructions


class TestProjectInventory:
    def test_merges_every_child_space(self, tmp_path):
        kb = _project_kb(
            tmp_path / "kb",
            {
                "PM": {"concepts/a.md": "x", "entities/e.md": "x"},
                "ENG": {"concepts/b.md": "x"},
            },
        )
        inv = project_inventory(kb)
        assert inv["concepts"] == ["PM/a", "ENG/b"] or set(inv["concepts"]) == {"PM/a", "ENG/b"}
        assert inv["entities"] == ["PM/e"]

    def test_names_are_space_qualified_so_spaces_cannot_collide(self, tmp_path):
        """Two spaces can each hold a concept of the same name; a flat merge
        would silently show one entry for two different pages."""
        kb = _project_kb(
            tmp_path / "kb",
            {"PM": {"concepts/order.md": "pm"}, "ENG": {"concepts/order.md": "eng"}},
        )
        assert sorted(project_inventory(kb)["concepts"]) == ["ENG/order", "PM/order"]

    def test_documents_carry_their_space(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        (kb / ".openkb" / "spaces" / "pm" / ".openkb" / "hashes.json").write_text(
            json.dumps({"h1": {"name": "doc.md", "type": "md"}}), encoding="utf-8"
        )
        inv = project_inventory(kb)
        assert inv["document_count"] == 1
        assert inv["documents"][0]["space"] == "PM"
        assert inv["documents"][0]["doc_name"] is None

    def test_confluence_documents_carry_source_type(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        child = kb / ".openkb" / "spaces" / "pm"
        (child / ".openkb" / "hashes.json").write_text(
            json.dumps(
                {
                    "h1": {
                        "name": "page.md",
                        "type": "md",
                        "path": ".openkb/sources/confluence/site/pm/page.md",
                    }
                }
            ),
            encoding="utf-8",
        )
        assert project_inventory(kb)["documents"][0]["source_type"] == "confluence"

    def test_confluence_document_uses_source_title(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        child = kb / ".openkb" / "spaces" / "pm"
        (child / ".openkb" / "hashes.json").write_text(
            json.dumps(
                {
                    "h1": {
                        "name": "confluence-site-pm-123.md",
                        "source_title": "Quy trình phê duyệt khoản vay",
                        "doc_name": "confluence-site-pm-123",
                        "type": "md",
                        "path": ".openkb/sources/confluence/site/pm/page.md",
                    }
                }
            ),
            encoding="utf-8",
        )
        assert project_inventory(kb)["documents"][0]["name"] == "Quy trình phê duyệt khoản vay"

    def test_legacy_confluence_document_uses_markdown_title(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        child = kb / ".openkb" / "spaces" / "pm"
        source = child / "wiki" / "sources" / "legacy.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('---\ntitle: "Tên page cũ"\n---\n\n# Nội dung\n', encoding="utf-8")
        (child / ".openkb" / "hashes.json").write_text(
            json.dumps(
                {
                    "h1": {
                        "name": "confluence-site-pm-123.md",
                        "doc_name": "legacy",
                        "type": "md",
                        "path": ".openkb/sources/confluence/site/pm/page.md",
                        "source_path": "wiki/sources/legacy.md",
                    }
                }
            ),
            encoding="utf-8",
        )
        assert project_inventory(kb)["documents"][0]["name"] == "Tên page cũ"

    def test_plain_kb_inventory_is_untouched(self, tmp_path):
        """Federation is project-only; a normal KB keeps bare stems."""
        kb = _plain_kb(tmp_path / "kb")
        (kb / "wiki" / "concepts").mkdir()
        (kb / "wiki" / "concepts" / "a.md").write_text("x", encoding="utf-8")
        from openkb.cli import get_kb_list

        assert get_kb_list(kb)["concepts"] == ["a"]
        assert is_project(kb) is False


class TestResolvePage:
    def test_space_qualified_path_routes_to_its_child_kb(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/a.md": "x"}})
        child, rel = resolve_page(kb, "concepts/PM/a")
        assert child == kb / ".openkb" / "spaces" / "pm"
        assert rel == "concepts/a"

    def test_agent_space_first_source_link_routes_to_its_child_kb(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"sources/page.md": "original"}})
        child, rel = resolve_page(kb, "PM/sources/page")
        assert child == kb / ".openkb" / "spaces" / "pm"
        assert rel == "sources/page"

    def test_agent_space_first_compiled_link_routes_to_its_child_kb(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/a.md": "compiled"}})
        child, rel = resolve_page(kb, "PM/concepts/a")
        assert child == kb / ".openkb" / "spaces" / "pm"
        assert rel == "concepts/a"

    def test_unqualified_path_stays_on_the_project(self, tmp_path):
        """A project's own files must still resolve — no silent redirection."""
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert resolve_page(kb, "index.md") == (kb, "index.md")
        assert resolve_page(kb, "concepts/a") == (kb, "concepts/a")

    def test_unknown_space_segment_is_not_treated_as_a_space(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert resolve_page(kb, "concepts/NOPE/a") == (kb, "concepts/NOPE/a")

    def test_non_merged_section_is_never_rewritten(self, tmp_path):
        """sources/ is not federated by name, so a PM-named folder under it
        must not be mistaken for a space reference."""
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert resolve_page(kb, "sources/PM/a") == (kb, "sources/PM/a")


class TestProjectIndex:
    def test_rolls_up_each_space(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {"concepts/a.md": "x"}})
        text = project_index(kb)
        assert "PM" in text
        assert "Concepts: 1" in text

    def test_explains_why_the_project_wiki_is_empty(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {"PM": {}})
        assert "not in the project's own wiki" in project_index(kb)

    def test_project_with_no_spaces_says_so(self, tmp_path):
        kb = _project_kb(tmp_path / "kb", {})
        assert "no Confluence spaces" in project_index(kb)
