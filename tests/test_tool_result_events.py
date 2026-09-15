"""Tests for the ``tool_result`` SSE event and its in-band failure detection.

The bug these lock down: OpenKB's read tools report "I could not read that" by
RETURNING a message rather than raising, so the Agents SDK sees every call
succeed. The UI had only ``tool_call`` to go on and painted a confirmed-read ✅
on reads that found nothing — a read of a path that does not exist looked
identical to a read that delivered content.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from openkb.agent.query import iter_agent_response_events
from openkb.agent.tools import is_tool_failure


class TestIsToolFailure:
    @pytest.mark.parametrize(
        "output",
        [
            "File not found: summaries/nope.md",
            "Access denied: path escapes wiki root.",
            "Image not found: images/x.png",
            "No files found.",
            "No content found for pages 3-5 in paper.",
            "Could not read /tmp/x: boom",
            "Unknown skill: 'nope'. Call list_skills() to see available skills.",
            "Unknown space: Space 'NOPE' is not assigned to this project",
            "Citation rejected: Quote is not present verbatim in the original document.",
        ],
    )
    def test_in_band_failures_are_detected(self, output):
        assert is_tool_failure(output) is True

    @pytest.mark.parametrize(
        "output",
        [
            "# Order book\n\nSome real page content.",
            "Written: output/deck.html",
            "PM concepts/x.md (score 3)",
            "No matches for 'zzz' in [PM]. Try different or broader terms.",
            "",
        ],
    )
    def test_real_output_is_not_a_failure(self, output):
        assert is_tool_failure(output) is False

    def test_non_string_output_is_not_a_failure(self):
        assert is_tool_failure(None) is False  # type: ignore[arg-type]


def _stream(*items):
    """Fake ``Runner.run_streamed`` result yielding the given RunItem events."""

    class _Result:
        final_output = "done"

        async def stream_events(self):
            for item in items:
                yield SimpleNamespace(item=item)

        def to_input_list(self):
            return []

    return _Result()


def _call(name, arguments, call_id):
    return SimpleNamespace(
        type="tool_call_item",
        raw_item=SimpleNamespace(name=name, arguments=arguments, call_id=call_id),
    )


def _output(call_id, output):
    return SimpleNamespace(
        type="tool_call_output_item",
        raw_item=SimpleNamespace(call_id=call_id),
        output=output,
    )


async def _events(monkeypatch, *items):
    """Drive iter_agent_response_events over a canned item stream."""
    import openkb.agent.query as q

    # RunItemStreamEvent/RawResponsesStreamEvent are imported inside the
    # function; isinstance against the fake namespace must land on the RunItem
    # branch, so stub the raw-response class to something nothing matches.
    monkeypatch.setattr(q, "Runner", SimpleNamespace(run_streamed=lambda *a, **k: _stream(*items)))
    import agents

    monkeypatch.setattr(agents, "RunItemStreamEvent", SimpleNamespace, raising=True)
    monkeypatch.setattr(agents, "RawResponsesStreamEvent", type("_Never", (), {}), raising=True)
    return [event async for event in iter_agent_response_events(object(), "q")]


class TestToolResultEvent:
    @pytest.mark.asyncio
    async def test_only_verified_quote_outputs_reach_final_citations(self, monkeypatch):
        valid = {
            "id": "quote1",
            "space": "PM",
            "path": "sources/loan.md",
            "title": "Loan",
            "quote": "The approved loan policy.",
            "start": 4,
            "end": 29,
        }
        second = {
            **valid,
            "id": "quote2",
            "path": "sources/risk.md",
            "title": "Risk",
        }
        events = await _events(
            monkeypatch,
            _call("quote_source", "{}", "c1"),
            _output("c1", json.dumps(valid)),
            _call("quote_source", "{}", "c3"),
            _output("c3", json.dumps(second)),
            _call("quote_source", "{}", "c2"),
            _output("c2", "Citation rejected: invented quote"),
        )
        final = events[-1]
        assert final["data"]["citations"] == [valid, second]

    @pytest.mark.asyncio
    async def test_successful_read_reports_ok(self, monkeypatch):
        events = await _events(
            monkeypatch,
            _call("read_file", '{"path": "summaries/x.md"}', "c1"),
            _output("c1", "# Real content"),
        )
        results = [e for e in events if e["event"] == "tool_result"]
        assert results == [
            {
                "event": "tool_result",
                "data": {
                    "name": "read_file",
                    "arguments": '{"path": "summaries/x.md"}',
                    "ok": True,
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_missing_file_read_reports_not_ok(self, monkeypatch):
        """The exact case the screenshot showed: a read of a path that is not in
        this KB, rendered as a confirmed read."""
        events = await _events(
            monkeypatch,
            _call("read_file", '{"path": "references/mcp-contract.md"}', "c1"),
            _output("c1", "File not found: references/mcp-contract.md"),
        )
        result = next(e for e in events if e["event"] == "tool_result")
        assert result["data"]["ok"] is False
        assert result["data"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_result_pairs_with_its_own_call(self, monkeypatch):
        """Two reads, one good and one bad: each result carries its own outcome."""
        events = await _events(
            monkeypatch,
            _call("read_file", '{"path": "a.md"}', "c1"),
            _output("c1", "content of a"),
            _call("read_file", '{"path": "b.md"}', "c2"),
            _output("c2", "File not found: b.md"),
        )
        results = [e["data"] for e in events if e["event"] == "tool_result"]
        assert [(r["arguments"], r["ok"]) for r in results] == [
            ('{"path": "a.md"}', True),
            ('{"path": "b.md"}', False),
        ]

    @pytest.mark.asyncio
    async def test_uncorrelated_output_emits_no_result(self, monkeypatch):
        """No matching call means no name to attribute the result to — stay
        silent rather than emit a nameless event the UI cannot place."""
        events = await _events(monkeypatch, _output("orphan", "File not found: x"))
        assert not [e for e in events if e["event"] == "tool_result"]
