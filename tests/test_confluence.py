from __future__ import annotations

import base64
import json
from unittest.mock import patch

from click.testing import CliRunner

from openkb.cli import cli
from openkb.confluence import (
    ConfluenceClient,
    ConfluencePage,
    storage_to_markdown,
    sync_confluence,
)
from openkb.state import HashRegistry


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def _page(*, body: str = "<p>Hello</p>", version: int = 1) -> ConfluencePage:
    return ConfluencePage(
        id="123",
        space_id="42",
        space_key="ENG",
        title="Architecture",
        version=version,
        updated_at="2026-09-09T00:00:00Z",
        parent_id=None,
        web_url="https://example.atlassian.net/wiki/spaces/ENG/pages/123",
        storage=body,
    )


class _Client:
    base_url = "https://example.atlassian.net"

    def __init__(self, pages):
        self.pages = pages

    def get_pages(self, _space):
        return list(self.pages)


def test_client_uses_basic_auth_and_follows_relative_pagination():
    requests = []
    payloads = [
        {
            "results": [{"id": "42", "key": "ENG"}],
            "_links": {"next": "/wiki/api/v2/spaces?cursor=x"},
        },
        {"results": [], "_links": {}},
    ]

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _Response(payloads.pop(0))

    client = ConfluenceClient(
        "https://example.atlassian.net/wiki", "dev@example.com", "secret", timeout=12
    )
    with patch("openkb.confluence.urllib.request.urlopen", side_effect=fake_urlopen):
        results = client._iter_results("spaces", {"keys": "ENG", "limit": 25})

    assert results == [{"id": "42", "key": "ENG"}]
    expected = base64.b64encode(b"dev@example.com:secret").decode()
    assert requests[0][0].headers["Authorization"] == f"Basic {expected}"
    assert requests[0][1] == 12
    assert requests[1][0].full_url.startswith(
        "https://example.atlassian.net/wiki/api/v2/spaces?cursor=x"
    )


def test_client_resolves_numeric_space_id_directly():
    client = ConfluenceClient("https://example.atlassian.net", "dev@example.com", "secret")
    with patch(
        "openkb.confluence.urllib.request.urlopen",
        return_value=_Response({"id": "42", "key": "ENG", "name": "Engineering"}),
    ) as urlopen:
        space = client.get_space("42")

    assert space["key"] == "ENG"
    assert urlopen.call_args.args[0].full_url.endswith("/wiki/api/v2/spaces/42")


def test_client_excludes_default_space_overview_scaffold():
    client = ConfluenceClient("https://example.atlassian.net", "dev@example.com", "secret")
    scaffold = (
        "<p>Click Edit to customize your overview</p>"
        "<p>Click Create at the top to create a page in your space</p>"
        "<p>What's your team's mission?</p>"
    )
    regular = "<p>Approved lending policy</p>"
    raw_pages = [
        {
            "id": "home",
            "title": "Engineering",
            "body": {"storage": {"value": scaffold}},
            "version": {"number": 1},
            "_links": {"webui": "/spaces/ENG/overview"},
        },
        {
            "id": "policy",
            "title": "Lending policy",
            "body": {"storage": {"value": regular}},
            "version": {"number": 1},
            "_links": {"webui": "/spaces/ENG/pages/policy"},
        },
    ]
    with (
        patch.object(client, "get_space", return_value={"id": "42", "key": "ENG"}),
        patch.object(client, "_iter_results", return_value=raw_pages),
    ):
        pages = client.get_pages("ENG")

    assert [page.id for page in pages] == ["policy"]


def test_storage_to_markdown_preserves_useful_structure():
    storage = (
        "<h2>Decision</h2><p>Use <strong>queues</strong> and "
        '<a href="https://example.com">the guide</a>.</p>'
        "<ul><li>Retry safely</li><li>Back off</li></ul>"
        '<ac:link><ri:page ri:content-title="Runbook" /></ac:link>'
        '<ri:attachment ri:filename="diagram.png" />'
    )
    rendered = storage_to_markdown(storage)
    assert "## Decision" in rendered
    assert "**queues**" in rendered
    assert "[the guide](https://example.com)" in rendered
    assert "- Retry safely" in rendered
    assert "Runbook" in rendered
    assert "[Attachment: diagram.png]" in rendered


def test_storage_to_markdown_formats_nested_lists_tables_and_ignores_macro_parameters():
    storage = (
        "<ul><li><p>Parent item</p><ul><li><p>Child item</p></li></ul></li></ul>"
        "<table><tr><th>Name</th><th>Status</th></tr>"
        "<tr><td>Loan</td><td><strong>Active</strong></td></tr></table>"
        '<ac:structured-macro ac:name="roadmap">'
        '<ac:parameter ac:name="data">true%7Bhuge-machine-payload</ac:parameter>'
        "</ac:structured-macro>"
    )

    rendered = storage_to_markdown(storage)

    assert "- Parent item" in rendered
    assert "  - Child item" in rendered
    assert "| Name | Status |" in rendered
    assert "| Loan | **Active** |" in rendered
    assert "huge-machine-payload" not in rendered


def test_storage_to_markdown_keeps_rich_text_but_drops_ui_widgets_and_controls():
    storage = (
        '<ac:structured-macro ac:name="panel"><ac:rich-text-body>'
        "<p>Important policy text</p></ac:rich-text-body></ac:structured-macro>"
        '<ac:structured-macro ac:name="status">'
        '<ac:parameter ac:name="title">Approved</ac:parameter>'
        '<ac:parameter ac:name="colour">Green</ac:parameter></ac:structured-macro>'
        '<ac:structured-macro ac:name="button">'
        '<ac:parameter ac:name="label">Edit</ac:parameter></ac:structured-macro>'
        '<button>Save</button><input value="internal control">'
    )

    rendered = storage_to_markdown(storage)

    assert "Important policy text" in rendered
    assert "Approved" in rendered
    assert "Edit" not in rendered
    assert "Save" not in rendered
    assert "internal control" not in rendered


def test_storage_to_markdown_deduplicates_confluence_smart_link_label():
    storage = (
        '<ac:link ac:card-appearance="inline">'
        '<ri:page ri:content-title="Risk policy" />'
        "<ac:link-body>Risk policy</ac:link-body></ac:link>"
    )

    assert storage_to_markdown(storage) == "Risk policy"


def test_storage_to_markdown_repairs_legacy_smart_quote_mojibake():
    assert storage_to_markdown("<p>Weâve updated it</p>") == "We’ve updated it"


def test_sync_is_incremental_and_token_is_never_persisted(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / ".openkb" / "hashes.json").write_text("{}")
    ingested = []
    removed = []

    def ingest(path, _kb):
        ingested.append(path.read_text(encoding="utf-8"))
        return "added"

    def remove(_kb, doc_name):
        removed.append(doc_name)
        return {"status": "removed"}

    first = sync_confluence(tmp_path, _Client([_page()]), ["ENG"], ingest=ingest, remove=remove)
    second = sync_confluence(tmp_path, _Client([_page()]), ["ENG"], ingest=ingest, remove=remove)
    third = sync_confluence(
        tmp_path,
        _Client([_page(body="<p>Changed</p>", version=2)]),
        ["ENG"],
        ingest=ingest,
        remove=remove,
    )

    assert (first.added, second.unchanged, third.updated) == (1, 1, 1)
    assert len(ingested) == 2
    assert removed == ["confluence-example-atlassian-net-eng-123"]
    persisted = "\n".join(
        p.read_text(encoding="utf-8") for p in (tmp_path / ".openkb").rglob("*") if p.is_file()
    )
    assert "secret" not in persisted
    manifest = json.loads((tmp_path / ".openkb" / "confluence-sync.json").read_text())
    assert next(iter(manifest["pages"].values()))["converter_version"] == 2


def test_sync_reprocesses_documents_created_by_an_older_converter(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / ".openkb" / "hashes.json").write_text("{}")
    ingested = []

    def ingest(path, _kb):
        ingested.append(path.name)
        return "added"

    first = sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=ingest,
        remove=lambda _kb, _doc: {"status": "removed"},
    )
    manifest_path = tmp_path / ".openkb" / "confluence-sync.json"
    manifest = json.loads(manifest_path.read_text())
    next(iter(manifest["pages"].values())).pop("converter_version")
    manifest_path.write_text(json.dumps(manifest))

    migrated = sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=ingest,
        remove=lambda _kb, _doc: {"status": "removed"},
    )

    assert first.added == 1
    assert migrated.updated == 1
    assert migrated.unchanged == 0
    assert len(ingested) == 2


def test_sync_persists_page_title_for_document_display(tmp_path):
    (tmp_path / ".openkb").mkdir()
    hashes_path = tmp_path / ".openkb" / "hashes.json"
    hashes_path.write_text("{}")

    def ingest(path, kb_dir):
        HashRegistry(hashes_path).add(
            "page-hash",
            {
                "name": path.name,
                "doc_name": path.stem,
                "type": "md",
                "path": path.relative_to(kb_dir).as_posix(),
                "source_path": "wiki/sources/page.md",
            },
        )
        return "added"

    sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=ingest,
        remove=lambda _kb, _doc: {"status": "removed"},
    )

    metadata = HashRegistry(hashes_path).get("page-hash")
    assert metadata is not None
    assert metadata["source_title"] == "Architecture"
    manifest = json.loads((tmp_path / ".openkb" / "confluence-sync.json").read_text())
    assert next(iter(manifest["pages"].values()))["title"] == "Architecture"


def test_sync_preserves_ingest_failure_detail(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / ".openkb" / "hashes.json").write_text("{}")

    result = sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=lambda _path, _kb: ("failed", "Invalid request parameter"),
        remove=lambda _kb, _doc: {"status": "removed"},
    )

    assert result.failed == 1
    assert result.errors == ["Architecture (123): compilation failed: Invalid request parameter"]


def test_delete_missing_is_scoped_and_opt_in(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / ".openkb" / "hashes.json").write_text("{}")
    removed = []

    def ingest(_path, _kb):
        return "added"

    sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=ingest,
        remove=lambda _kb, _doc: {"status": "removed"},
    )
    kept = sync_confluence(
        tmp_path,
        _Client([]),
        ["ENG"],
        ingest=ingest,
        remove=lambda _kb, doc: removed.append(doc) or {"status": "removed"},
    )
    deleted = sync_confluence(
        tmp_path,
        _Client([]),
        ["ENG"],
        delete_missing=True,
        ingest=ingest,
        remove=lambda _kb, doc: removed.append(doc) or {"status": "removed"},
    )
    assert kept.deleted == 0
    assert deleted.deleted == 1
    assert removed == ["confluence-example-atlassian-net-eng-123"]


def test_sync_reports_the_page_that_failed_compilation(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / ".openkb" / "hashes.json").write_text("{}")

    result = sync_confluence(
        tmp_path,
        _Client([_page()]),
        ["ENG"],
        ingest=lambda _path, _kb: "failed",
        remove=lambda _kb, _doc: {"status": "removed"},
    )

    assert result.failed == 1
    assert result.errors == ["Architecture (123): compilation failed"]


def test_cli_requires_token_from_environment(tmp_path):
    (tmp_path / ".openkb").mkdir()
    (tmp_path / "wiki").mkdir()
    runner = CliRunner()
    with (
        patch("openkb.cli._find_kb_dir", return_value=tmp_path),
        patch("openkb.cli._setup_llm_key"),
        patch("openkb.cli.resolve_effective_config", return_value=({}, {})),
        patch.dict("os.environ", {}, clear=True),
    ):
        result = runner.invoke(
            cli,
            [
                "sync",
                "confluence",
                "--base-url",
                "https://example.atlassian.net",
                "--email",
                "dev@example.com",
                "--space",
                "ENG",
            ],
        )
    assert result.exit_code == 1
    assert "CONFLUENCE_API_TOKEN" in result.output
