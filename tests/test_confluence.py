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
