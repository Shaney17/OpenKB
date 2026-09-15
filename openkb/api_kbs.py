"""KB discovery for ``GET /api/v1/kbs`` (the web UI's KB switcher).

Split out of :mod:`openkb.api_helpers` so that module stays under the per-file
line gate (``tests/test_file_size.py``). Discovery unions the children of
``kb_root_dir()`` with the KBs registered in global.yaml (``kb_aliases`` /
``known_kbs``), so a KB created outside the root — the CLI initializes a KB
wherever it is run — is still surfaced.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from openkb.api_helpers import _is_kb_dir
from openkb.config import kb_root_dir, registered_kbs
from openkb.spaces import configured_spaces, space_dir


def _direct_confluence_spaces(kb_dir: Path) -> list[str] | None:
    """Return CLI-synced space keys, or None when this KB has no sync manifest.

    A direct ``openkb sync confluence`` writes confluence-sync.json, not the
    project/child-space config. Treating only configured child spaces as a
    Confluence source mislabeled these standalone KBs as local files.
    """
    path = kb_dir / ".openkb" / "confluence-sync.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        spaces = data.get("last_spaces", []) if isinstance(data, dict) else []
        return [str(space) for space in spaces if isinstance(space, str)]
    except (OSError, ValueError):
        return []


def _kb_list_item(kb_dir: Path, name: str) -> dict[str, Any]:
    """Build one KB-list item: name + resolved path + rollup counters.

    ``document_count`` comes from ``.openkb/hashes.json`` (0 if absent/corrupt)
    and ``last_compile`` from the newest ``wiki/summaries/*.md`` mtime. For a
    Confluence project both are rolled up from its child space KBs, which is
    where its content actually lives.
    """
    # A Confluence project keeps its documents in child space KBs, so its own
    # hashes.json is empty and the switcher showed a fully-synced project as
    # "0". Roll the children up instead.
    spaces = configured_spaces(kb_dir)
    direct_spaces = _direct_confluence_spaces(kb_dir) if not spaces else None
    roots = [space_dir(kb_dir, key) for key in sorted(spaces)] or [kb_dir]
    doc_count = 0
    for root in roots:
        hashes_file = root / ".openkb" / "hashes.json"
        if hashes_file.exists():
            try:
                doc_count += len(json.loads(hashes_file.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    last_compile = None
    mtimes: list[float] = []
    for root in roots:
        summaries_dir = root / "wiki" / "summaries"
        if not summaries_dir.is_dir():
            continue
        # Guard each stat() (like document_count above): a single unstattable
        # entry — e.g. a dangling symlink whose target was removed — must not
        # throw out of the whole /kbs listing and 500 every other KB.
        for p in summaries_dir.glob("*.md"):
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                continue
    if mtimes:
        last_compile = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(max(mtimes)))
    statuses = {str(space.get("status") or "idle") for space in spaces.values()}
    if "running" in statuses:
        sync_status = "running"
    elif "failed" in statuses:
        sync_status = "failed"
    elif "partial" in statuses:
        sync_status = "partial"
    elif statuses == {"succeeded"}:
        sync_status = "succeeded"
    else:
        sync_status = "idle" if spaces else None
    is_confluence = bool(spaces) or direct_spaces is not None
    source_labels = (
        [str(space.get("label") or key) for key, space in sorted(spaces.items())]
        if spaces
        else direct_spaces or []
    )
    return {
        "name": name,
        "path": str(kb_dir),
        "document_count": doc_count,
        "last_compile": last_compile,
        "has_raw": (kb_dir / "raw").is_dir(),
        "source_type": "confluence" if is_confluence else "local",
        "space_count": len(spaces) if spaces else len(direct_spaces or []),
        "source_labels": source_labels,
        "sync_status": sync_status,
    }


def _list_knowledge_bases() -> dict[str, Any]:
    """List knowledge bases for the web UI's KB switcher.

    Discovery unions two sources and de-dupes by RESOLVED path so a KB that is
    both a root child and registered appears exactly once:

    1. children of ``kb_root_dir()`` that look like a KB (``_is_kb_dir``); and
    2. KBs registered in global.yaml (``kb_aliases`` name→path, then
       ``known_kbs`` paths) that live OUTSIDE the root.

    Root children are visited first, so a dual-source KB keeps its directory
    name (which equals the alias for KBs created via ``/init``); a registry-only
    KB keeps its alias name (or, for a bare ``known_kbs`` path, its directory
    name). ``registered_kbs()`` already yields collision-resolved UNIQUE names
    (a bare ``known_kbs`` entry colliding with a root child's basename is hidden
    there), so names here are unique too; the by-name guard below is a
    belt-and-suspenders backstop. Stale/missing registry entries (fail
    ``_is_kb_dir``) are skipped. The response still carries the top-level
    ``root``.
    """
    root = kb_root_dir()
    seen_paths: set[str] = set()
    seen_names: set[str] = set()
    items: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not _is_kb_dir(child):
                continue
            resolved = child.resolve()
            seen_paths.add(str(resolved))
            seen_names.add(child.name)
            items.append(_kb_list_item(resolved, child.name))
    for name, kb_dir in registered_kbs():
        if str(kb_dir) in seen_paths or name in seen_names or not _is_kb_dir(kb_dir):
            continue
        seen_paths.add(str(kb_dir))
        seen_names.add(name)
        items.append(_kb_list_item(kb_dir, name))
    return {"root": str(root), "knowledge_bases": items}
