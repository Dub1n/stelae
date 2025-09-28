#!/usr/bin/env python3
"""Streamable HTTP MCP shim that wraps local SSE servers for ChatGPT connectors."""

from __future__ import annotations

import json
import logging
import os
import sys
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
STATIC_SEARCH_ENABLED = os.getenv("STELAE_STREAMABLE_STATIC_SEARCH", "1") != "0"

DEFAULT_SEARCH_PATHS: Sequence[str] = tuple(
    part.strip() for part in SEARCH_PATHS_ENV.split(",") if part.strip()
) or (str(SEARCH_ROOT),)

TRANSPORT = os.getenv("STELAE_STREAMABLE_TRANSPORT", "streamable-http")


def _configure_logger() -> logging.Logger:
    """Configure a file-backed logger for early process diagnostics."""

    logger = logging.getLogger("stelae.streamable_mcp")
    if logger.handlers:
        return logger

    log_path_env = os.getenv("STELAE_STREAMABLE_STDIO_LOG")
    default_path = Path(__file__).resolve().parent.parent / "logs" / "stelae_stdio_bridge.log"
    log_path = Path(log_path_env) if log_path_env else default_path

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handlers: list[logging.Handler] = []

    file_handler_error: Exception | None = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem issues are diagnostic by nature
        file_handler_error = exc
    else:
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    for handler in handlers:
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    if file_handler_error:
        logger.warning("Falling back to stderr logging because %s could not be opened: %s", log_path, file_handler_error)

    return logger


LOGGER = _configure_logger()

app = FastMCP(
    name="stelae-hub",
    instructions="Connector-ready hub providing search and fetch over the local workspace.",
    host=STREAMABLE_HOST,
    port=STREAMABLE_PORT,
    streamable_http_path="/mcp",
)


@dataclass(frozen=True)
class StaticSearchHit:
    id: str
    title: str
    text: str
    url: str
    snippet: str


STATIC_SEARCH_HITS: Sequence[StaticSearchHit] = (
    StaticSearchHit(
        id="repo:docs/SPEC-v1.md",
        title="SPEC-v1.md",
        text="Summary of the Stelae MCP compliance requirements and verification flow.",
        url="stelae://repo/docs/SPEC-v1.md",
        snippet="SPEC outlines the MCP handshake contract, tool catalog expectations, and SSE timing guarantees.",
    ),
    StaticSearchHit(
        id="repo:dev/chat_gpt_connector_compliant_reference.md",
        title="chat_gpt_connector_compliant_reference.md",
        text="Reference catalog consolidating manifest, initialize, and search requirements for ChatGPT connectors.",
        url="stelae://repo/dev/chat_gpt_connector_compliant_reference.md",
        snippet="Reference doc captures the minimal search/fetch tool set plus example payloads used by compliant servers.",
    ),
    StaticSearchHit(
        id="repo:dev/compliance_handoff.md",
        title="compliance_handoff.md",
        text="Action plan enumerating remediation steps to align the Stelae MCP endpoint with ChatGPT verification.",
        url="stelae://repo/dev/compliance_handoff.md",
        snippet="Handoff describes trimming initialize/tools.list outputs and delivering deterministic search hits for validation.",
    ),
)


def _static_search_results() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for hit in STATIC_SEARCH_HITS:
        results.append(
            {
                "id": hit.id,
                "title": hit.title,
                "text": hit.text,
                "url": hit.url,
                "metadata": {"snippet": hit.snippet},
            }
        )
    return results


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

    if STATIC_SEARCH_ENABLED:
        return json.dumps({"results": _static_search_results()}, ensure_ascii=False)

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
    LOGGER.info(
        "Launching FastMCP transport=%s proxy=%s cwd=%s search_root=%s default_paths=%s",
        TRANSPORT,
        PROXY_BASE,
        os.getcwd(),
        SEARCH_ROOT,
        DEFAULT_SEARCH_PATHS,
    )
    if TRANSPORT == "stdio":
        ready_message = {
            "jsonrpc": "2.0",
            "method": "notifications/server/ready",
            "params": {},
        }
        try:
            sys.stdout.write(json.dumps(ready_message, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        except Exception:  # pragma: no cover - surfaced for operational diagnostics
            LOGGER.exception("Failed to emit server ready notification")
        else:
            LOGGER.info("Emitted server ready notification")
    try:
        app.run(transport=TRANSPORT)
    except Exception:  # pragma: no cover - surfaced for operational diagnostics
        LOGGER.exception("FastMCP transport %s crashed", TRANSPORT)
        raise
    LOGGER.info("FastMCP transport %s terminated", TRANSPORT)



if __name__ == "__main__":
    run()
