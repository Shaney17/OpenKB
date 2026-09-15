"""Confluence Cloud source synchronization.

This module deliberately uses the Python standard library for HTTP.  It keeps
Atlassian credentials out of persisted source state, normalizes Confluence
storage XHTML into stable Markdown files, and feeds changed pages through the
same add/remove pipeline as local documents.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, TypeAlias

from openkb.locks import atomic_write_json, atomic_write_text
from openkb.state import HashRegistry

_MANIFEST_VERSION = 1
_USER_AGENT = "openkb/confluence-sync"

IngestOutcome: TypeAlias = str | tuple[str, str | None]


class ConfluenceError(RuntimeError):
    """A safe, user-facing Confluence synchronization error."""


@dataclass(frozen=True)
class ConfluencePage:
    id: str
    space_id: str
    space_key: str
    title: str
    version: int
    updated_at: str
    parent_id: str | None
    web_url: str
    storage: str


@dataclass
class SyncResult:
    discovered: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class ConfluenceClient:
    """Small Confluence Cloud REST v2 client using Basic API-token auth."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        timeout: float = 30,
        max_retries: int = 4,
    ) -> None:
        parsed = urllib.parse.urlparse(base_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Confluence base URL must be an absolute http(s) URL")
        # Users commonly paste either the site root or its /wiki URL.
        path = parsed.path.rstrip("/")
        if path.endswith("/wiki"):
            path = path[:-5]
        self.base_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, path, "", "", "")
        ).rstrip("/")
        self.api_root = f"{self.base_url}/wiki/api/v2"
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._authorization = f"Basic {token}"
        self.timeout = timeout
        self.max_retries = max_retries

    def _safe_url(self, path_or_url: str, params: dict[str, Any] | None = None) -> str:
        if urllib.parse.urlparse(path_or_url).scheme:
            url = path_or_url
        elif path_or_url.startswith("/"):
            url = urllib.parse.urljoin(f"{self.base_url}/", path_or_url)
        else:
            url = urllib.parse.urljoin(f"{self.api_root}/", path_or_url)
        parsed = urllib.parse.urlparse(url)
        base = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raise ConfluenceError("Confluence pagination attempted to leave the configured site")
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            url = urllib.parse.urlunparse(parsed._replace(query=query))
        return url

    def _get_json(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict:
        url = self._safe_url(path_or_url, params)
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": self._authorization,
                    "Accept": "application/json",
                    "User-Agent": _USER_AGENT,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ConfluenceError("Confluence returned a non-object JSON response")
                    return payload
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    retry_after = exc.headers.get("Retry-After", "1")
                    try:
                        delay = max(0.0, min(float(retry_after), 60.0))
                    except ValueError:
                        delay = min(2**attempt, 60)
                    time.sleep(delay)
                    continue
                if exc.code in (401, 403):
                    raise ConfluenceError(
                        f"Confluence authentication/permission failed (HTTP {exc.code})"
                    ) from exc
                raise ConfluenceError(f"Confluence request failed (HTTP {exc.code})") from exc
            except urllib.error.URLError as exc:
                raise ConfluenceError(f"Could not reach Confluence: {exc.reason}") from exc
            except json.JSONDecodeError as exc:
                raise ConfluenceError("Confluence returned invalid JSON") from exc
        raise ConfluenceError("Confluence retry limit reached")

    def _iter_results(self, path: str, params: dict[str, Any]) -> list[dict]:
        results: list[dict] = []
        next_url: str | None = path
        next_params: dict[str, Any] | None = params
        while next_url:
            payload = self._get_json(next_url, next_params)
            batch = payload.get("results", [])
            if not isinstance(batch, list):
                raise ConfluenceError("Confluence response has an invalid results field")
            results.extend(item for item in batch if isinstance(item, dict))
            links = payload.get("_links") or {}
            raw_next = links.get("next") if isinstance(links, dict) else None
            next_url = str(raw_next) if raw_next else None
            next_params = None
        return results

    def get_space(self, identifier: str) -> dict:
        if identifier.strip().isdigit():
            space = self._get_json(f"spaces/{urllib.parse.quote(identifier.strip(), safe='')}")
            if space.get("id"):
                return space
            raise ConfluenceError(f"Confluence space not found or not visible: {identifier}")
        key = identifier.strip()
        spaces = self._iter_results("spaces", {"keys": key, "limit": 25})
        for space in spaces:
            if str(space.get("key", "")).casefold() == key.casefold():
                return space
        raise ConfluenceError(f"Confluence space not found or not visible: {key}")

    def get_pages(self, space_key: str) -> list[ConfluencePage]:
        space = self.get_space(space_key)
        space_id = str(space.get("id", ""))
        canonical_key = str(space.get("key") or space_key)
        if not space_id:
            raise ConfluenceError(f"Confluence space has no id: {space_key}")
        raw_pages = self._iter_results(
            f"spaces/{urllib.parse.quote(space_id, safe='')}/pages",
            {"limit": 250, "status": "current", "body-format": "storage", "depth": "all"},
        )
        pages: list[ConfluencePage] = []
        for raw in raw_pages:
            page_id = str(raw.get("id", ""))
            if not page_id:
                continue
            body = raw.get("body") or {}
            storage = body.get("storage") if isinstance(body, dict) else {}
            storage_value = storage.get("value", "") if isinstance(storage, dict) else ""
            version = raw.get("version") or {}
            page_links = raw.get("_links") or {}
            webui = page_links.get("webui", "") if isinstance(page_links, dict) else ""
            pages.append(
                ConfluencePage(
                    id=page_id,
                    space_id=space_id,
                    space_key=canonical_key,
                    title=str(raw.get("title") or f"Confluence page {page_id}"),
                    version=int(version.get("number") or 0) if isinstance(version, dict) else 0,
                    updated_at=(
                        str(version.get("createdAt") or "") if isinstance(version, dict) else ""
                    ),
                    parent_id=str(raw["parentId"]) if raw.get("parentId") else None,
                    web_url=urllib.parse.urljoin(f"{self.base_url}/wiki/", str(webui)),
                    storage=str(storage_value or ""),
                )
            )
        return pages


class _StorageToMarkdown(HTMLParser):
    """Conservative Confluence storage-XHTML to Markdown renderer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hrefs: list[str | None] = []
        self.list_stack: list[str] = []
        self.in_pre = 0
        self.skip_depth = 0

    def _newline(self, count: int = 1) -> None:
        current = "".join(self.parts)
        needed = count - (len(current) - len(current.rstrip("\n")))
        if needed > 0:
            self.parts.append("\n" * needed)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._newline(2)
            self.parts.append("#" * int(tag[1]) + " ")
        elif tag in ("p", "div"):
            self._newline(2)
        elif tag == "br":
            self._newline()
        elif tag in ("strong", "b"):
            self.parts.append("**")
        elif tag in ("em", "i"):
            self.parts.append("*")
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")
        elif tag == "pre":
            self._newline(2)
            self.parts.append("```\n")
            self.in_pre += 1
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
            self._newline()
        elif tag == "li":
            self._newline()
            marker = "1. " if self.list_stack and self.list_stack[-1] == "ol" else "- "
            self.parts.append("  " * max(0, len(self.list_stack) - 1) + marker)
        elif tag == "blockquote":
            self._newline(2)
            self.parts.append("> ")
        elif tag == "a":
            self.parts.append("[")
            self.hrefs.append(attr.get("href"))
        elif tag == "img":
            alt = attr.get("alt") or "image"
            src = attr.get("src") or ""
            self.parts.append(f"![{alt}]({src})" if src else f"[{alt}]")
        elif tag == "tr":
            self._newline()
        elif tag in ("th", "td"):
            self.parts.append(" | ")
        elif tag == "ri:attachment":
            filename = attr.get("ri:filename") or attr.get("filename")
            if filename:
                self.parts.append(f"[Attachment: {filename}]")
        elif tag == "ri:page":
            title = attr.get("ri:content-title") or attr.get("content-title")
            if title:
                self.parts.append(title)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in ("p", "div", "blockquote"):
            self._newline(2)
        elif tag in ("strong", "b"):
            self.parts.append("**")
        elif tag in ("em", "i"):
            self.parts.append("*")
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")
        elif tag == "pre":
            self.in_pre = max(0, self.in_pre - 1)
            self._newline()
            self.parts.append("```\n")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self._newline(2)
        elif tag == "a":
            href = self.hrefs.pop() if self.hrefs else None
            self.parts.append(f"]({href})" if href else "]")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_pre:
            self.parts.append(data)
        else:
            self.parts.append(re.sub(r"\s+", " ", data))

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def storage_to_markdown(storage: str) -> str:
    parser = _StorageToMarkdown()
    parser.feed(storage)
    parser.close()
    return parser.markdown()


def render_page(page: ConfluencePage) -> str:
    """Render one page with stable provenance included in the content hash."""
    metadata = {
        "source": "confluence",
        "space_key": page.space_key,
        "space_id": page.space_id,
        "page_id": page.id,
        "version": page.version,
        "updated_at": page.updated_at,
        "parent_id": page.parent_id or "",
        "source_url": page.web_url,
        "title": page.title,
    }
    frontmatter = "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()
    )
    body = storage_to_markdown(page.storage)
    return f"---\n{frontmatter}\n---\n\n# {page.title}\n\n{body}\n"


def _slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return result or "source"


def _source_path(kb_dir: Path, base_url: str, page: ConfluencePage) -> Path:
    host = urllib.parse.urlparse(base_url).netloc
    name = f"confluence-{_slug(host)}-{_slug(page.space_key)}-{_slug(page.id)}.md"
    return (
        kb_dir / ".openkb" / "sources" / "confluence" / _slug(host) / _slug(page.space_key) / name
    )


def _manifest_path(kb_dir: Path) -> Path:
    return kb_dir / ".openkb" / "confluence-sync.json"


def _load_manifest(kb_dir: Path) -> dict:
    path = _manifest_path(kb_dir)
    if not path.exists():
        return {"version": _MANIFEST_VERSION, "pages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfluenceError(f"Invalid Confluence sync manifest: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        raise ConfluenceError(f"Invalid Confluence sync manifest shape: {path}")
    return data


def _registered_doc_name(kb_dir: Path, source_path: Path) -> str:
    registry = HashRegistry(kb_dir / ".openkb" / "hashes.json")
    try:
        key = source_path.resolve().relative_to(kb_dir.resolve()).as_posix()
    except ValueError:
        key = str(source_path.resolve())
    meta = registry.get_by_path(key)
    return str(meta.get("doc_name")) if meta and meta.get("doc_name") else source_path.stem


def _set_registered_source_title(kb_dir: Path, doc_name: str, title: str) -> None:
    """Persist a Confluence page title without changing its stable wiki name.

    ``doc_name`` is an internal identifier used by compiled artifacts and
    wikilinks, so renaming it when a Confluence title changes would break
    references.  ``source_title`` is the human-facing name exposed by the API.
    """
    registry = HashRegistry(kb_dir / ".openkb" / "hashes.json")
    for file_hash, current in registry.all_entries().items():
        if current.get("doc_name") != doc_name:
            continue
        if current.get("source_title") == title:
            return
        metadata = dict(current)
        metadata["source_title"] = title
        registry.add(file_hash, metadata)
        return


def sync_confluence(
    kb_dir: Path,
    client: ConfluenceClient,
    space_keys: list[str],
    *,
    delete_missing: bool = False,
    dry_run: bool = False,
    ingest: Callable[[Path, Path], IngestOutcome] | None = None,
    remove: Callable[[Path, str], dict] | None = None,
) -> SyncResult:
    """Synchronize selected spaces into an initialized OpenKB knowledge base."""
    if not space_keys:
        raise ValueError("At least one Confluence space key is required")
    if ingest is None or remove is None:
        # Runtime import avoids making this low-level source module depend on
        # Click and avoids an import cycle while openkb.cli defines commands.
        from openkb.cli import add_single_file, run_remove_for_api

        ingest = ingest or (lambda path, root: add_single_file(path, root))
        remove = remove or (lambda root, doc: run_remove_for_api(root, doc))

    selected = {key.casefold() for key in space_keys}
    fetched: list[tuple[ConfluencePage, str]] = []
    # Fetch the complete remote snapshot before any local mutation. A failed
    # request can therefore never look like mass deletion.
    for space_key in space_keys:
        fetched.extend((page, space_key) for page in client.get_pages(space_key))

    result = SyncResult(discovered=len(fetched))
    manifest = _load_manifest(kb_dir)
    entries: dict[str, dict] = manifest["pages"]
    seen: set[str] = set()

    for page, space_ref in fetched:
        identity = f"{urllib.parse.urlparse(client.base_url).netloc}:{page.space_id}:{page.id}"
        seen.add(identity)
        rendered = render_page(page)
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        previous = entries.get(identity)
        if previous and previous.get("content_hash") == digest:
            doc_name = str(previous.get("doc_name") or "")
            if doc_name:
                _set_registered_source_title(kb_dir, doc_name, page.title)
            if previous.get("title") != page.title:
                previous["title"] = page.title
                atomic_write_json(_manifest_path(kb_dir), manifest)
            result.unchanged += 1
            continue
        if dry_run:
            if previous:
                result.updated += 1
            else:
                result.added += 1
            continue

        source_path = _source_path(kb_dir, client.base_url, page)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(source_path, rendered)

        was_update = previous is not None
        if previous is not None:
            removal = remove(kb_dir, str(previous.get("doc_name") or source_path.stem))
            if removal.get("status") not in ("removed", "not_found"):
                result.failed += 1
                result.errors.append(f"{page.title} ({page.id}): could not replace old version")
                continue
        ingest_result = ingest(source_path, kb_dir)
        if isinstance(ingest_result, tuple):
            outcome, failure_detail = ingest_result
        else:
            outcome, failure_detail = ingest_result, None
        if outcome not in ("added", "skipped"):
            result.failed += 1
            suffix = f": {failure_detail}" if failure_detail else ""
            result.errors.append(f"{page.title} ({page.id}): compilation failed{suffix}")
            continue
        doc_name = _registered_doc_name(kb_dir, source_path)
        _set_registered_source_title(kb_dir, doc_name, page.title)
        entries[identity] = {
            "base_url": client.base_url,
            "space_id": page.space_id,
            "space_key": page.space_key,
            "space_ref": space_ref,
            "page_id": page.id,
            "version": page.version,
            "content_hash": digest,
            "doc_name": doc_name,
            "title": page.title,
            "source_path": source_path.relative_to(kb_dir).as_posix(),
        }
        atomic_write_json(_manifest_path(kb_dir), manifest)
        if was_update:
            result.updated += 1
        else:
            result.added += 1

    if delete_missing:
        stale = [
            identity
            for identity, entry in entries.items()
            if entry.get("base_url") == client.base_url
            and str(entry.get("space_ref") or entry.get("space_key", "")).casefold() in selected
            and identity not in seen
        ]
        for identity in stale:
            entry = entries[identity]
            if dry_run:
                result.deleted += 1
                continue
            removal = remove(kb_dir, str(entry.get("doc_name", "")))
            if removal.get("status") not in ("removed", "not_found"):
                result.failed += 1
                result.errors.append(
                    f"Page {entry.get('page_id', identity)}: could not remove deleted page"
                )
                continue
            source_rel = entry.get("source_path")
            if isinstance(source_rel, str):
                candidate = (kb_dir / source_rel).resolve()
                source_root = (kb_dir / ".openkb" / "sources" / "confluence").resolve()
                if candidate.is_relative_to(source_root):
                    candidate.unlink(missing_ok=True)
            del entries[identity]
            atomic_write_json(_manifest_path(kb_dir), manifest)
            result.deleted += 1

    if not dry_run:
        manifest["version"] = _MANIFEST_VERSION
        manifest["last_base_url"] = client.base_url
        manifest["last_spaces"] = list(space_keys)
        atomic_write_json(_manifest_path(kb_dir), manifest)
    return result
