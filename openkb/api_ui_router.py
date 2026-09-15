"""Same-origin web UI session bootstrap."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request, Response, status

from openkb.api_helpers import UI_SESSION_COOKIE, _ui_session_value

ui_router = APIRouter()


@ui_router.post("/api/v1/ui/session", status_code=status.HTTP_204_NO_CONTENT)
async def ui_session_endpoint(request: Request, response: Response) -> None:
    """Bootstrap the same-origin web UI without exposing the API token."""
    api_token = os.environ.get("OPENKB_API_TOKEN")
    if api_token:
        response.set_cookie(
            UI_SESSION_COOKIE,
            _ui_session_value(api_token),
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=24 * 60 * 60,
            path="/",
        )
