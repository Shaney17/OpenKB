"""Only exact quotations in original source documents become citations."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from openkb.api import create_app
from openkb.citations import read_citation_source, verify_source_quote

QUOTE = "The loan is approved after a risk review."


def test_quote_is_exact_and_frontmatter_is_not_citable(kb_dir):
    (kb_dir / "wiki" / "sources" / "loan.md").write_text(
        f'---\ntitle: "Loan Policy"\n---\n\n# Rules\n\n{QUOTE}\n', encoding="utf-8"
    )
    citation = verify_source_quote(kb_dir, "sources/loan.md", QUOTE)

    assert citation["title"] == "Loan Policy"
    assert citation["path"] == "sources/loan.md"
    assert (
        read_citation_source(kb_dir, "sources/loan.md")["content"][
            citation["start"] : citation["end"]
        ]
        == QUOTE
    )
    with pytest.raises(ValueError, match="verbatim"):
        verify_source_quote(kb_dir, "sources/loan.md", QUOTE.replace("approved", "accepted"))
    with pytest.raises(ValueError, match="verbatim"):
        verify_source_quote(kb_dir, "sources/loan.md", 'title: "Loan Policy"')


@pytest.mark.parametrize(
    "path",
    [
        "summaries/loan.md",
        "concepts/loan.md",
        "index.md",
        "../sources/loan.md",
        "sources/images/x.md",
    ],
)
def test_derived_or_unsafe_paths_are_rejected(kb_dir, path):
    (kb_dir / "wiki" / "summaries" / "loan.md").write_text(QUOTE)
    (kb_dir / "wiki" / "sources" / "loan.md").write_text(QUOTE)
    with pytest.raises(ValueError, match="original sources"):
        verify_source_quote(kb_dir, path, QUOTE)


def test_long_document_quotes_are_taken_from_original_page_content(kb_dir):
    (kb_dir / "wiki" / "sources" / "paper.json").write_text(
        json.dumps([{"page": 1, "content": "Context."}, {"page": 2, "content": QUOTE}])
    )
    citation = verify_source_quote(kb_dir, "sources/paper.json", QUOTE)
    assert citation["title"] == "paper"
    assert citation["start"] > 0


def test_project_quote_resolves_only_within_selected_space(kb_dir):
    child = kb_dir / ".openkb" / "spaces" / "pm"
    (child / "wiki" / "sources").mkdir(parents=True)
    (child / "wiki" / "sources" / "loan.md").write_text(QUOTE)
    (kb_dir / ".openkb" / "confluence-project.json").write_text(
        json.dumps(
            {
                "version": 1,
                "connection": {},
                "spaces": {"PM": {"ref": "PM", "key": "PM", "confluence_id": "123", "label": "PM"}},
            }
        )
    )

    citation = verify_source_quote(kb_dir, "sources/loan.md", QUOTE, "PM")
    assert citation["space"] == "PM"
    with pytest.raises(ValueError, match="not assigned"):
        verify_source_quote(kb_dir, "sources/loan.md", QUOTE, "ENG")


def test_citation_viewer_returns_exact_highlight_and_rejects_changed_quote(monkeypatch, kb_dir):
    (kb_dir / "wiki" / "sources" / "loan.md").write_text(f"# Loan\n\n{QUOTE}\n")
    monkeypatch.setenv("OPENKB_API_TOKEN", "secret")
    monkeypatch.setattr("openkb.api_helpers.resolve_kb_alias", lambda _kb: kb_dir)
    client = TestClient(create_app())
    body = {"kb": "test", "path": "sources/loan.md", "quote": QUOTE}
    headers = {"Authorization": "Bearer secret"}

    response = client.post("/api/v1/citation/source", json=body, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"][payload["start"] : payload["end"]] == QUOTE
    assert payload["title"] == "Loan"

    changed = client.post(
        "/api/v1/citation/source",
        json={**body, "quote": QUOTE.replace("approved", "accepted")},
        headers=headers,
    )
    assert changed.status_code == 409
    derived = client.post(
        "/api/v1/citation/source",
        json={**body, "path": "summaries/loan.md"},
        headers=headers,
    )
    assert derived.status_code == 404
