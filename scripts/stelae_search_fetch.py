#!/usr/bin/env python3
"""Connector-compliant MCP server exposing search and fetch."""

import json
import asyncio
import os
from pathlib import Path
from typing import List, Optional

import httpx
from mcp import types
from mcp.server import FastMCP

MCP_PROXY_BASE = os.getenv("STELAE_MCP_PROXY_BASE", "http://localhost:9090")
MCP_GREP_PATH = os.getenv("STELAE_MCP_GREP_PATH", "/rg/mcp")
SEARCH_ROOT = Path(os.getenv("STELAE_SEARCH_ROOT", ".")).resolve()
MAX_BYTES = int(os.getenv("STELAE_MAX_BYTES", "1048576"))

server = FastMCP(name="stelae-search-fetch")

def _safe_repo_path(rel_path: str) -> Path:
    candidate = (SEARCH_ROOT / rel_path).resolve()
    try:
        candidate.relative_to(SEARCH_ROOT)
    except ValueError as exc:
        raise FileNotFoundError(rel_path) from exc
    return candidate

async def _call_mcp(path: str, tool_name: str, arguments: dict) -> dict:
    url = f"{MCP_PROXY_BASE.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "type": "callTool",
            "toolName": tool_name,
            "arguments": arguments,
        }
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

@server.tool(
    name="search",
    description="Connector-compliant search over the repository.")
async def search(query: str, globs: Optional[List[str]] = None, max_results: int = 50) -> types.TextContent:
    arguments = {
        "query": query,
        "paths": [str(SEARCH_ROOT)],
        "globs": globs or [],
        "max_results": max_results,
    }
    raw = await _call_mcp(MCP_GREP_PATH, "search", arguments)
    matches = []
    structured = raw.get("structuredContent")
    if isinstance(structured, dict):
        matches = structured.get("matches", []) or []
    results = []
    for match in matches:
        rel_path = match.get("path") or ""
        if not isinstance(rel_path, str) or not rel_path:
            continue
        line = match.get("line") or 1
        result_id = f"repo:{rel_path}#L{line}"
        result = {
            "id": result_id,
            "title": rel_path,
            "url": f"stelae://repo/{rel_path}#L{line}",
        }
        snippet = match.get("text")
        if snippet:
            result["metadata"] = {"snippet": snippet}
        results.append(result)
        if len(results) >= max_results:
            break
    payload = json.dumps({"results": results}, ensure_ascii=False)
    return types.TextContent(type="text", text=payload)

@server.tool(
    name="fetch",
    description="Connector-compliant fetch for search results.")
async def fetch(target: str) -> types.TextContent:
    result_id = target or ""
    remainder = result_id[len("repo:") :] if result_id.startswith("repo:") else result_id
    rel_path, _, line_part = remainder.partition("#L")
    line_number = int(line_part) if line_part.isdigit() else None
    try:
        disk_path = _safe_repo_path(rel_path)
        text = disk_path.read_text(encoding="utf-8", errors="ignore")
    except (FileNotFoundError, OSError):
        disk_path = None
        text = ""
    if len(text) > MAX_BYTES:
        text = text[:MAX_BYTES]
    metadata = {}
    if line_number is not None:
        metadata["line"] = line_number
    document = {
        "id": result_id,
        "title": rel_path,
        "text": text,
        "url": f"stelae://repo/{rel_path}",
        "metadata": metadata,
    }
    if disk_path is None:
        document["metadata"]["error"] = "file not found"
    payload = json.dumps(document, ensure_ascii=False)
    return types.TextContent(type="text", text=payload)

async def main():
    await server.run("stdio")

if __name__ == "__main__":
    asyncio.run(main())
