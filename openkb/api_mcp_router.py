"""Small stateless Streamable HTTP MCP facade for remote OpenKB agents."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from openkb.api_helpers import _resolve_kb, require_bearer_only
from openkb.api_kbs import _list_knowledge_bases
from openkb.cli import get_kb_list
from openkb.confluence_projects import public_project
from openkb.spaces import read_space_page, search_spaces, space_dir

mcp_router = APIRouter()


def _result(payload: Any) -> dict[str, Any]:
    import json

    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


TOOLS = [
    {
        "name": "openkb_list_projects",
        "description": "List OpenKB projects visible to this server.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "openkb_list_spaces",
        "description": (
            "List Confluence spaces assigned to an OpenKB project and their sync status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "required": ["project"],
        },
    },
    {
        "name": "openkb_get_inventory",
        "description": (
            "List concepts, entities, summaries, reports and documents in one project space."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}, "space": {"type": "string"}},
            "required": ["project", "space"],
        },
    },
    {
        "name": "openkb_search",
        "description": "Search compiled wiki pages across all or selected spaces in a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "query": {"type": "string"},
                "spaces": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["project", "query"],
        },
    },
    {
        "name": "openkb_read_page",
        "description": "Read a compiled Markdown wiki page from one project space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "space": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["project", "space", "path"],
        },
    },
]


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "openkb_list_projects":
        return _result(_list_knowledge_bases())
    project = str(args.get("project") or "")
    if not project:
        return _error("project is required")
    project_dir = _resolve_kb(project)
    try:
        if name == "openkb_list_spaces":
            return _result(public_project(project_dir))
        if name == "openkb_get_inventory":
            return _result(get_kb_list(space_dir(project_dir, str(args.get("space") or ""))))
        if name == "openkb_search":
            query = str(args.get("query") or "").strip()
            if not query:
                return _error("query is required")
            spaces = args.get("spaces")
            selected = [str(item) for item in spaces] if isinstance(spaces, list) else None
            limit = max(1, min(int(args.get("limit", 10)), 50))
            return _result({"matches": search_spaces(project_dir, query, selected, limit)})
        if name == "openkb_read_page":
            space = str(args.get("space") or "")
            path = str(args.get("path") or "")
            return _result(
                {
                    "space": args.get("space"),
                    "path": path,
                    "content": read_space_page(project_dir, space, path),
                }
            )
        return _error(f"Unknown tool: {name}")
    except (ValueError, FileNotFoundError, OSError) as exc:
        return _error(str(exc))


@mcp_router.post("/mcp")
async def mcp_endpoint(request: Request, _: None = Depends(require_bearer_only)):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC request") from exc
    method = body.get("method")
    request_id = body.get("id")
    result: Any
    if method == "notifications/initialized":
        return JSONResponse(status_code=202, content={})
    if method == "initialize":
        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "openkb", "version": "1"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = body.get("params") or {}
        result = _call(str(params.get("name") or ""), params.get("arguments") or {})
    else:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            },
        )
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
