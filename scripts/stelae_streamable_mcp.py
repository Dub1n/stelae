#!/usr/bin/env python3
"""Streamable HTTP MCP shim that wraps local SSE servers for ChatGPT connectors."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import anyio
import httpx
from mcp import types
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.server import FastMCP

DEFAULT_PROXY_BASE = "http://localhost:9090"
DEFAULT_STREAMABLE_HOST = "0.0.0.0"
DEFAULT_STREAMABLE_PORT = 9100
DEFAULT_SEARCH_MAX_RESULTS = 50
DEFAULT_FETCH_MAX_LENGTH = 5000
DEFAULT_SSE_TIMEOUT = 10.0
DEFAULT_SSE_READ_TIMEOUT = 120.0

PROXY_BASE = os.getenv("STELAE_PROXY_BASE", DEFAULT_PROXY_BASE).rstrip("/")
SEARCH_ROOT = Path(os.getenv("STELAE_SEARCH_ROOT", os.getcwd())).resolve()
SEARCH_PATHS_ENV = os.getenv("STELAE_STREAMABLE_SEARCH_PATHS", str(SEARCH_ROOT))
STREAMABLE_HOST = os.getenv("STELAE_STREAMABLE_HOST", DEFAULT_STREAMABLE_HOST)
STREAMABLE_PORT = int(os.getenv("STELAE_STREAMABLE_PORT", str(DEFAULT_STREAMABLE_PORT)))
SEARCH_MAX_RESULTS = int(os.getenv("STELAE_STREAMABLE_MAX_RESULTS", str(DEFAULT_SEARCH_MAX_RESULTS)))
FETCH_MAX_LENGTH = int(os.getenv("STELAE_STREAMABLE_FETCH_MAX_LENGTH", str(DEFAULT_FETCH_MAX_LENGTH)))
SSE_TIMEOUT = float(os.getenv("STELAE_STREAMABLE_SSE_TIMEOUT", str(DEFAULT_SSE_TIMEOUT)))
SSE_READ_TIMEOUT = float(os.getenv("STELAE_STREAMABLE_SSE_READ_TIMEOUT", str(DEFAULT_SSE_READ_TIMEOUT)))

DEFAULT_SEARCH_PATHS: Sequence[str] = tuple(
    part.strip() for part in SEARCH_PATHS_ENV.split(",") if part.strip()
) or (str(SEARCH_ROOT),)

app = FastMCP(
    name="stelae-hub",
    instructions="Connector-ready hub providing search and fetch over the local workspace.",
    host=STREAMABLE_HOST,
    port=STREAMABLE_PORT,
    streamable_http_path="/mcp",
)


@dataclass(slots=True)
class CallResult:
    """Lightweight representation of an upstream CallToolResult."""

    content: List[types.TextContent]
    structured_content: Dict[str, Any] | None

    @classmethod
    def from_call_tool_result(cls, result: types.CallToolResult) -> "CallResult":
        text_content = [item for item in result.content if isinstance(item, types.TextContent)]
        return cls(content=text_content, structured_content=result.structuredContent)


async def _call_upstream_tool(
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    read_timeout: float = SSE_READ_TIMEOUT,
) -> CallResult:
    endpoint = f"{PROXY_BASE}/{server_name}/sse"
    async with sse_client(endpoint, timeout=SSE_TIMEOUT, sse_read_timeout=read_timeout) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"{server_name}.{tool_name} returned an error")
            return CallResult.from_call_tool_result(result)


def _coerce_paths(paths: Sequence[str] | str | None) -> Sequence[str | os.PathLike[str]]:
    if not paths:
        return DEFAULT_SEARCH_PATHS
    if isinstance(paths, str):
        return (paths,)
    return tuple(paths)


def _to_repo_id(file_path: str, line_number: int | None) -> str:
    rel = _relative_repo_path(file_path)
    suffix = f"#L{line_number}" if line_number else ""
    return f"repo:{rel}{suffix}"


def _relative_repo_path(file_path: str) -> str:
    try:
        path_obj = Path(file_path)
        rel = path_obj.resolve().relative_to(SEARCH_ROOT)
        return str(rel)
    except Exception:
        return file_path


@app.tool(name="search", description="Connector-compliant source search over the workspace.")
async def search(
    query: str,
    max_results: int = SEARCH_MAX_RESULTS,
    paths: Sequence[str] | str | None = None,
    ignore_case: bool = False,
) -> str:
    """Return connector-ready search results."""

    query = query.strip()
    if not query:
        return json.dumps({"results": []})

    effective_paths = _coerce_paths(paths)
    max_results = max(1, min(max_results, SEARCH_MAX_RESULTS))

    arguments: Dict[str, Any] = {
        "pattern": query,
        "paths": list(effective_paths) if len(effective_paths) > 1 else effective_paths[0],
        "recursive": True,
        "line_number": True,
        "max_count": max_results,
        "ignore_case": ignore_case,
    }

    upstream = await _call_upstream_tool("rg", "grep", arguments)

    matches: List[Dict[str, Any]] = []
    for content in upstream.content:
        try:
            data = json.loads(content.text)
            if isinstance(data, list):
                matches.extend(data)
        except json.JSONDecodeError:
            continue

    results: List[Dict[str, Any]] = []
    for match in matches:
        file_path = match.get("file") or match.get("path")
        if not isinstance(file_path, str):
            continue
        line_num = match.get("line_num") or match.get("line")
        try:
            line_val = int(line_num) if line_num is not None else None
        except (TypeError, ValueError):
            line_val = None
        snippet = match.get("line") or match.get("text") or ""
        entry = {
            "id": _to_repo_id(file_path, line_val),
            "title": _relative_repo_path(file_path),
            "url": f"stelae://repo/{_relative_repo_path(file_path)}"
            + (f"#L{line_val}" if line_val else ""),
            "metadata": {"snippet": snippet.strip()},
        }
        results.append(entry)
        if len(results) >= max_results:
            break

    return json.dumps({"results": results}, ensure_ascii=False)


async def _maybe_refetch_raw(
    url: str,
    max_length: int,
    start_index: int,
    original_text: str,
) -> str | None:
    error_markers = ("ExtractArticle.js", "readabilipy", "Failed to parse")
    if any(marker in original_text for marker in error_markers):
        fallback = await _call_upstream_tool(
            "fetch",
            "fetch",
            {"url": url, "max_length": max_length, "start_index": start_index, "raw": True},
            read_timeout=180.0,
        )
        for content in fallback.content:
            if content.text:
                return content.text
    return None


@app.tool(name="fetch", description="Connector-compliant fetch built atop Docy/fetch servers.")
async def fetch(
    url: str,
    max_length: int = FETCH_MAX_LENGTH,
    start_index: int = 0,
    raw: bool = False,
) -> str:
    arguments = {
        "url": url,
        "max_length": max_length,
        "start_index": start_index,
        "raw": raw,
    }
    upstream = await _call_upstream_tool("fetch", "fetch", arguments, read_timeout=180.0)

    payload_text = ""
    for content in upstream.content:
        if content.text:
            payload_text = content.text
            break

    if not payload_text:
        payload_text = json.dumps(
            {
                "id": url,
                "title": url,
                "text": "",
                "url": url,
                "metadata": {"note": "Empty response from upstream fetch server"},
            },
            ensure_ascii=False,
        )

    if not raw:
        fallback = await _maybe_refetch_raw(url, max_length, start_index, payload_text)
        if fallback is not None:
            payload_text = fallback

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        data = {
            "id": url,
            "title": url,
            "text": payload_text,
            "url": url,
            "metadata": {"raw": True if raw else False, "note": "Non-JSON fetch response"},
        }
    else:
        data.setdefault("id", url)
        data.setdefault("title", data.get("url", url))
        data.setdefault("url", url)
        data.setdefault("metadata", {})

    return json.dumps(data, ensure_ascii=False)


def run() -> None:
    app.run(transport="streamable-http")


if __name__ == "__main__":
    run()
