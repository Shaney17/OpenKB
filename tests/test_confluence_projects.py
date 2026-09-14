from __future__ import annotations

import json

from fastapi.testclient import TestClient

from openkb.api import create_app
from openkb.cli import initialize_kb
from openkb.confluence_projects import (
    add_space,
    child_kb_dir,
    load_project,
    public_project,
    remove_space,
)


def _configure_confluence(project):
    (project / ".env").write_text(
        "CONFLUENCE_BASE_URL=https://example.atlassian.net\n"
        "CONFLUENCE_EMAIL=admin@example.com\n"
        "CONFLUENCE_API_TOKEN=token\n",
        encoding="utf-8",
    )


def test_project_can_hold_multiple_isolated_spaces(tmp_path):
    project = tmp_path / "project"
    initialize_kb(project, register=False)

    add_space(
        project,
        space_id="101",
    )
    add_space(
        project,
        space_id="202",
    )

    assert set(load_project(project)["spaces"]) == {"101", "202"}
    assert child_kb_dir(project, "101") != child_kb_dir(project, "202")
    assert (child_kb_dir(project, "101") / "wiki" / "index.md").is_file()
    assert (child_kb_dir(project, "202") / "wiki" / "index.md").is_file()


def test_removing_space_retains_compiled_child(tmp_path):
    project = tmp_path / "project"
    initialize_kb(project, register=False)
    add_space(
        project,
        space_id="101",
    )
    child = child_kb_dir(project, "101")

    assert remove_space(project, "101") is True
    assert child.is_dir()
    assert public_project(project)["spaces"] == []


def test_api_add_space_only_requires_the_space_id(monkeypatch, tmp_path):
    project = tmp_path / "project"
    initialize_kb(project, register=False)
    _configure_confluence(project)
    monkeypatch.setenv("OPENKB_API_TOKEN", "server-secret")
    monkeypatch.setattr("openkb.api_helpers.resolve_kb_alias", lambda _value: project)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/confluence/spaces",
        headers={"Authorization": "Bearer server-secret"},
        json={"project": "demo", "space_id": "12345"},
    )

    assert response.status_code == 201
    assert response.json()["space"]["ref"] == "12345"
    assert load_project(project)["connection"] == {}


def test_api_sync_all_queues_every_project_space(monkeypatch, tmp_path):
    project = tmp_path / "project"
    initialize_kb(project, register=False)
    _configure_confluence(project)
    add_space(project, space_id="101")
    add_space(project, space_id="202")
    monkeypatch.setenv("OPENKB_API_TOKEN", "server-secret")
    monkeypatch.setattr("openkb.api_helpers.resolve_kb_alias", lambda _value: project)
    queued = []

    def capture(_project, keys):
        queued.extend(keys)

    monkeypatch.setattr("openkb.api_confluence_router._run_all_spaces", capture)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/confluence/spaces/sync-all",
        headers={"Authorization": "Bearer server-secret"},
        json={"project": "demo"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": ["101", "202"], "skipped": 0}
    assert queued == ["101", "202"]
    from openkb.api_confluence_router import _running

    _running.clear()


def test_mcp_search_is_project_and_space_scoped(monkeypatch, tmp_path):
    project = tmp_path / "project"
    initialize_kb(project, register=False)
    for key in ("ENG", "OPS"):
        add_space(
            project,
            space_id=key,
        )
    (child_kb_dir(project, "ENG") / "wiki" / "concepts" / "release.md").write_text(
        "Release train alpha", encoding="utf-8"
    )
    (child_kb_dir(project, "OPS") / "wiki" / "concepts" / "release.md").write_text(
        "Release train beta", encoding="utf-8"
    )
    monkeypatch.setenv("OPENKB_API_TOKEN", "secret")
    monkeypatch.setattr("openkb.api_helpers.resolve_kb_alias", lambda value: project)
    client = TestClient(create_app())
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer secret"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "openkb_search",
                "arguments": {"project": "demo", "query": "release", "spaces": ["ENG"]},
            },
        },
    )

    assert response.status_code == 200
    result = json.loads(response.json()["result"]["content"][0]["text"])
    assert {hit["space"] for hit in result["matches"]} == {"ENG"}


def test_mcp_requires_server_bearer_token(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENKB_API_TOKEN", "secret")
    client = TestClient(create_app())
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401


def test_mcp_does_not_accept_web_ui_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENKB_API_TOKEN", "secret")
    client = TestClient(create_app())
    assert client.post("/api/v1/ui/session").status_code == 204

    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == 401
