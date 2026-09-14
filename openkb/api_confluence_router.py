"""REST endpoints for project-scoped Confluence space administration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from openkb.api_helpers import _resolve_kb, require_bearer_token
from openkb.cli import add_single_file, run_remove_for_api
from openkb.config import resolve_credential_bundle
from openkb.confluence import ConfluenceClient, ConfluenceError, sync_confluence
from openkb.confluence_projects import (
    add_space,
    connection_for,
    ensure_child_kb,
    load_project,
    mark_sync,
    public_project,
    remove_space,
    token_for,
)

confluence_router = APIRouter()
_running: set[str] = set()


def _ingest_with_error_detail(path: Path, root: Path, *, bundle) -> tuple[str, str | None]:
    errors: list[str] = []
    outcome = add_single_file(
        path,
        root,
        bundle=bundle,
        on_error=lambda exc: errors.append(str(exc)),
    )
    return outcome, errors[-1] if errors else None


class SpaceCreate(BaseModel):
    project: str = Field(..., min_length=1)
    space_id: str = Field(..., min_length=1)


class SpaceAction(BaseModel):
    project: str = Field(..., min_length=1)
    space_id: str = Field(..., min_length=1)


class ProjectAction(BaseModel):
    project: str = Field(..., min_length=1)


def _run_space_sync(project_dir: Path, key: str) -> None:
    run_key = f"{project_dir.resolve()}::{key}"
    try:
        connection = connection_for(project_dir)
        token = token_for(project_dir)
        if not token:
            raise ConfluenceError("CONFLUENCE_API_TOKEN is not configured on the server")
        client = ConfluenceClient(
            connection.get("base_url", ""),
            connection.get("email", ""),
            token,
        )
        remote_space = client.get_space(key)
        child = ensure_child_kb(project_dir, key)
        bundle = resolve_credential_bundle(project_dir)
        result = sync_confluence(
            child,
            client,
            [key],
            delete_missing=True,
            ingest=lambda path, root: _ingest_with_error_detail(path, root, bundle=bundle),
            remove=lambda root, doc: run_remove_for_api(root, doc),
        )
        payload = {
            "discovered": result.discovered,
            "added": result.added,
            "updated": result.updated,
            "unchanged": result.unchanged,
            "deleted": result.deleted,
            "failed": result.failed,
        }
        completed = result.added + result.updated + result.unchanged + result.deleted
        status = "succeeded" if not result.failed else "partial" if completed else "failed"
        from datetime import datetime, timezone

        mark_sync(
            project_dir,
            key,
            status,
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=payload,
            error="; ".join(result.errors[:5]) or None,
            failed_pages=result.errors,
            confluence_id=str(remote_space.get("id") or key),
            key=str(remote_space.get("key") or key),
            label=str(remote_space.get("name") or remote_space.get("key") or key),
        )
    except Exception as exc:
        from datetime import datetime, timezone

        mark_sync(
            project_dir,
            key,
            "failed",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
    finally:
        _running.discard(run_key)


@confluence_router.get("/api/v1/confluence/projects")
async def list_spaces_endpoint(project: str = Query(...), _: None = Depends(require_bearer_token)):
    return public_project(_resolve_kb(project))


@confluence_router.post("/api/v1/confluence/spaces", status_code=201)
async def add_space_endpoint(request: SpaceCreate, _: None = Depends(require_bearer_token)):
    project_dir = _resolve_kb(request.project)
    try:
        connection = connection_for(project_dir)
        if not connection["base_url"] or not connection["email"]:
            raise ValueError(
                "Set CONFLUENCE_BASE_URL and CONFLUENCE_EMAIL in the server .env first"
            )
        space = await asyncio.to_thread(add_space, project_dir, space_id=request.space_id)
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(
            status_code=409 if isinstance(exc, FileExistsError) else 400, detail=str(exc)
        ) from exc
    return {"space": space}


@confluence_router.delete("/api/v1/confluence/spaces")
async def remove_space_endpoint(request: SpaceAction, _: None = Depends(require_bearer_token)):
    removed = await asyncio.to_thread(remove_space, _resolve_kb(request.project), request.space_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Confluence space is not configured")
    return {"removed": True, "data_retained": True}


@confluence_router.post("/api/v1/confluence/spaces/sync", status_code=202)
async def sync_space_endpoint(
    request: SpaceAction,
    background: BackgroundTasks,
    _: None = Depends(require_bearer_token),
):
    project_dir = _resolve_kb(request.project)
    key = request.space_id.strip().upper()
    if key not in load_project(project_dir)["spaces"]:
        raise HTTPException(status_code=404, detail="Confluence space is not configured")
    run_key = f"{project_dir.resolve()}::{key}"
    if run_key in _running:
        raise HTTPException(status_code=409, detail="This space is already syncing")
    _running.add(run_key)
    from datetime import datetime, timezone

    mark_sync(
        project_dir,
        key,
        "running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        error=None,
    )
    background.add_task(_run_space_sync, project_dir, key)
    return {"accepted": True, "space_id": key}


def _run_all_spaces(project_dir: Path, keys: list[str]) -> None:
    for key in keys:
        _run_space_sync(project_dir, key)


@confluence_router.post("/api/v1/confluence/spaces/sync-all", status_code=202)
async def sync_all_spaces_endpoint(
    request: ProjectAction,
    background: BackgroundTasks,
    _: None = Depends(require_bearer_token),
):
    project_dir = _resolve_kb(request.project)
    keys = list(load_project(project_dir)["spaces"])
    if not keys:
        raise HTTPException(status_code=400, detail="This project has no Confluence spaces")
    accepted = []
    from datetime import datetime, timezone

    for key in keys:
        run_key = f"{project_dir.resolve()}::{key}"
        if run_key in _running:
            continue
        _running.add(run_key)
        mark_sync(
            project_dir,
            key,
            "running",
            last_started_at=datetime.now(timezone.utc).isoformat(),
            error=None,
        )
        accepted.append(key)
    if accepted:
        background.add_task(_run_all_spaces, project_dir, accepted)
    return {"accepted": accepted, "skipped": len(keys) - len(accepted)}
