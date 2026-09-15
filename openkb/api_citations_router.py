"""Read-only citation viewer for verified original documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from openkb.api_helpers import _resolve_kb, require_bearer_token
from openkb.api_models import CitationSourceRequest, CitationSourceResponse
from openkb.citations import read_citation_source

citations_router = APIRouter()


@citations_router.post("/api/v1/citation/source", response_model=CitationSourceResponse)
async def citation_source_endpoint(
    request: CitationSourceRequest,
    _: None = Depends(require_bearer_token),
) -> CitationSourceResponse:
    kb_dir = _resolve_kb(request.kb)
    try:
        source = await run_in_threadpool(read_citation_source, kb_dir, request.path, request.space)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=404, detail="Original source document not found.") from exc
    start = source["content"].find(request.quote)
    if start < 0:
        raise HTTPException(status_code=409, detail="Quote has changed in the original document.")
    return CitationSourceResponse(
        title=source["title"],
        content=source["content"],
        start=start,
        end=start + len(request.quote),
    )
