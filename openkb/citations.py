"""Verbatim citations from ingested documents, never compiled wiki pages."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from openkb.frontmatter import parse as parse_frontmatter
from openkb.spaces import space_dir


def _source_file(kb_dir: Path, path: str, space: str) -> Path:
    root = space_dir(kb_dir, space) if space else kb_dir
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 2
        or relative.parts[0] != "sources"
        or relative.suffix not in (".md", ".json")
    ):
        raise ValueError("Citation must point to an original sources/ document.")
    sources = (root / "wiki" / "sources").resolve()
    target = (root / "wiki" / Path(*relative.parts)).resolve()
    if not target.is_relative_to(sources) or not target.is_file():
        raise FileNotFoundError("Original source document not found.")
    return target


def read_citation_source(kb_dir: Path, path: str, space: str = "") -> dict[str, str]:
    """Read one source artifact with a safe, wiki-relative path."""
    target = _source_file(kb_dir, path, space)
    if target.suffix == ".json":
        pages = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(pages, list):
            raise ValueError("Invalid original source document.")
        content = "\n\n---\n\n".join(
            str(page.get("content", "")).strip()
            for page in pages
            if isinstance(page, dict) and str(page.get("content", "")).strip()
        )
        title = target.stem
    else:
        content = target.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        title = frontmatter.get("title") if isinstance(frontmatter.get("title"), str) else ""
        title = title or target.stem
        if content.startswith("---\n"):
            boundary = content.find("\n---\n", 4)
            if boundary >= 0:
                content = content[boundary + 5 :].lstrip("\n")
        if title == target.stem:
            heading = re.search(r"^# (.+)$", content, re.MULTILINE)
            if heading:
                title = heading.group(1).strip()
    return {"content": content, "title": title}


def verify_source_quote(kb_dir: Path, path: str, quote: str, space: str = "") -> dict[str, Any]:
    """Accept only an exact substring of an original converted source."""
    if not 12 <= len(quote) <= 1500 or not quote.strip():
        raise ValueError("Quote must be 12–1500 characters of verbatim source text.")
    source = read_citation_source(kb_dir, path, space)
    start = source["content"].find(quote)
    if start < 0:
        raise ValueError("Quote is not present verbatim in the original document.")
    identifier = hashlib.sha256(f"{space}\0{path}\0{quote}".encode()).hexdigest()[:16]
    return {
        "id": identifier,
        "space": space,
        "path": path,
        "title": source["title"],
        "quote": quote,
        "start": start,
        "end": start + len(quote),
    }
