"""Project-scoped Confluence space configuration and child KB management."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from openkb.cli import get_kb_list, initialize_kb
from openkb.locks import atomic_write_json, atomic_write_text

_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.").lower()
    if not slug or slug in {".", ".."}:
        raise ValueError("Invalid Confluence space key")
    return slug


def project_path(project_dir: Path) -> Path:
    return project_dir / ".openkb" / "confluence-project.json"


def load_project(project_dir: Path) -> dict[str, Any]:
    path = project_path(project_dir)
    if not path.exists():
        return {"version": _VERSION, "connection": {}, "spaces": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Confluence project configuration: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("spaces", {}), dict):
        raise ValueError(f"Invalid Confluence project configuration: {path}")
    data.setdefault("version", _VERSION)
    data.setdefault("connection", {})
    data.setdefault("spaces", {})
    return data


def save_project(project_dir: Path, data: dict[str, Any]) -> None:
    data["version"] = _VERSION
    atomic_write_json(project_path(project_dir), data)


def child_kb_dir(project_dir: Path, space_key: str) -> Path:
    return project_dir / ".openkb" / "spaces" / _slug(space_key)


def _copy_parent_runtime(project_dir: Path, child: Path) -> None:
    config = project_dir / ".openkb" / "config.yaml"
    if config.is_file():
        atomic_write_text(child / ".openkb" / "config.yaml", config.read_text(encoding="utf-8"))
    env = project_dir / ".env"
    if env.is_file():
        target = child / ".env"
        atomic_write_text(target, env.read_text(encoding="utf-8"))
        target.chmod(0o600)


def ensure_child_kb(project_dir: Path, space_key: str) -> Path:
    child = child_kb_dir(project_dir, space_key)
    if not (child / ".openkb").is_dir():
        initialize_kb(child, register=False)
    # Refresh shared model/provider settings before every sync. This prevents a
    # child created with an old or invalid LLM key from remaining permanently
    # stuck in partial status after the project credentials are corrected.
    _copy_parent_runtime(project_dir, child)
    return child


def token_for(project_dir: Path) -> str | None:
    values = dotenv_values(project_dir / ".env") if (project_dir / ".env").is_file() else {}
    import os

    return (
        str(values.get("CONFLUENCE_API_TOKEN") or os.environ.get("CONFLUENCE_API_TOKEN") or "")
        or None
    )


def connection_for(project_dir: Path) -> dict[str, str]:
    """Resolve the single Confluence site/email shared by every project space."""
    values = dotenv_values(project_dir / ".env") if (project_dir / ".env").is_file() else {}
    import os

    legacy = load_project(project_dir).get("connection") or {}
    return {
        "base_url": str(
            values.get("CONFLUENCE_BASE_URL")
            or os.environ.get("CONFLUENCE_BASE_URL")
            or legacy.get("base_url")
            or ""
        ).rstrip("/"),
        "email": str(
            values.get("CONFLUENCE_EMAIL")
            or os.environ.get("CONFLUENCE_EMAIL")
            or legacy.get("email")
            or ""
        ),
    }


def add_space(project_dir: Path, *, space_id: str) -> dict[str, Any]:
    key = space_id.strip().upper()
    if not key:
        raise ValueError("Confluence space ID is required")
    data = load_project(project_dir)
    spaces = data["spaces"]
    if key in spaces:
        raise FileExistsError(f"Space {key} is already in this project")
    ensure_child_kb(project_dir, key)
    spaces[key] = {
        "ref": key,
        "key": key,
        "confluence_id": key if key.isdigit() else None,
        "label": key,
        "status": "idle",
        "created_at": _now(),
        "last_started_at": None,
        "last_finished_at": None,
        "last_result": None,
        "error": None,
    }
    save_project(project_dir, data)
    return spaces[key]


def remove_space(project_dir: Path, space_key: str) -> bool:
    """Detach a space from future syncs without deleting its compiled child KB."""
    data = load_project(project_dir)
    removed = data["spaces"].pop(space_key.strip().upper(), None) is not None
    if removed:
        save_project(project_dir, data)
    return removed


def public_project(project_dir: Path) -> dict[str, Any]:
    data = load_project(project_dir)
    connection = connection_for(project_dir)
    items = []
    for key, raw in sorted(data["spaces"].items()):
        child = child_kb_dir(project_dir, key)
        inventory = get_kb_list(child) if (child / ".openkb").is_dir() else None
        item = dict(raw)
        item["ref"] = key
        item["key"] = str(item.get("key") or key)
        item["label"] = str(item.get("label") or item["key"])
        if item.get("status") not in {"idle", "running", "succeeded", "partial", "failed"}:
            item["status"] = "idle"
        item["inventory"] = inventory
        items.append(item)
    return {
        "connection": {
            "base_url": connection.get("base_url", ""),
            "email": connection.get("email", ""),
            "token_configured": token_for(project_dir) is not None,
            "configured": bool(connection.get("base_url") and connection.get("email")),
        },
        "spaces": items,
    }


def mark_sync(project_dir: Path, space_key: str, status: str, **updates: Any) -> None:
    data = load_project(project_dir)
    entry = data["spaces"].get(space_key)
    if not entry:
        return
    entry["status"] = status
    entry.update(updates)
    save_project(project_dir, data)
