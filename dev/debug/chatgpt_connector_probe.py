#!/usr/bin/env python3
"""Minimal Streamable-HTTP probe to emulate ChatGPT connector handshake."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
import urllib.parse
import httpx

DEFAULT_SERVER_URL = "https://mcp.infotopology.xyz/mcp"
DEFAULT_TIMEOUT = 20.0


def _event_stream_lines(text: str):
    # split by \n, keep simple
    for line in text.splitlines():
        yield line.rstrip("\r")


async def timed(
    name: str, coro, *, output: Optional[Callable[[str], None]] = print
) -> Tuple[float, Any]:
    start = time.perf_counter()
    result = await coro
    duration = time.perf_counter() - start
    if output:
        output(f"[{name}] {duration:.3f}s")
    return duration, result


async def fetch_session_endpoint(
    client: httpx.AsyncClient, server_url: str, timeout: float
) -> str:
    """Open the SSE facade and return the per-session endpoint"""
    headers = {"Accept": "text/event-stream"}
    async with client.stream(
        "GET", server_url, headers=headers, timeout=timeout
    ) as resp:
        resp.raise_for_status()
        event: Optional[str] = None
        data: Optional[str] = None
        async for chunk in resp.aiter_text():
            for line in _event_stream_lines(chunk):
                if line.startswith("event: "):
                    event = line[len("event: ") :].strip()
                elif line.startswith("data: "):
                    data = line[len("data: ") :].strip()
                elif line == "":
                    if event == "endpoint" and data:
                        # First try JSON (our own facade can emit JSON payloads)
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            parsed = None
                        if isinstance(parsed, dict):
                            endpoint_url = parsed.get("endpoint")
                            if endpoint_url:
                                return endpoint_url

                        # Fall back to the standard FastMCP format: a URL-encoded path/query
                        decoded = urllib.parse.unquote(data)
                        if decoded.startswith(("http://", "https://")):
                            return decoded
                        endpoint_url = urllib.parse.urljoin(server_url, decoded)
                        return endpoint_url
                    event = None
                    data = None
        raise RuntimeError("SSE stream closed without endpoint event")


@dataclass
class JsonRpcResult:
    status_code: int
    headers: Dict[str, str]
    payload: Dict[str, Any] | None


async def post_rpc(
    client: httpx.AsyncClient, endpoint: str, payload: Dict[str, Any], timeout: float
) -> JsonRpcResult:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    resp = await client.post(endpoint, headers=headers, json=payload, timeout=timeout)
    text = resp.text.strip()
    parsed: Dict[str, Any] | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"_raw": text}
    return JsonRpcResult(
        status_code=resp.status_code, headers=dict(resp.headers), payload=parsed
    )


async def run_probe(
    server_url: str, timeout: float, *, output: Optional[Callable[[str], None]] = print
) -> Dict[str, Any]:
    async with httpx.AsyncClient(http2=True, timeout=timeout) as client:
        if output:
            output(f"Opening SSE session at {server_url}")
        _, endpoint = await timed(
            "sse-open",
            fetch_session_endpoint(client, server_url, timeout),
            output=output,
        )
        if output:
            output(f"Session endpoint: {endpoint}")

        initialize_payload = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "chatgpt-probe", "version": "0.1"},
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {},
                    "prompts": {},
                    "resources": {},
                    "tools": {},
                },
            },
        }

        if output:
            output("Sending initialize")
        init_duration, init_result = await timed(
            "initialize",
            post_rpc(client, endpoint, initialize_payload, timeout),
            output=output,
        )
        if output:
            output(
                f"initialize -> {init_result.status_code} ({init_duration:.3f}s)\n"
                f"{json.dumps(init_result.payload, indent=2)}"
            )

        if output:
            output("Sending notifications/initialized")
        note_payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        note_duration, note_result = await timed(
            "notifications/initialized",
            post_rpc(client, endpoint, note_payload, timeout),
            output=output,
        )
        if output:
            output(
                f"notifications/initialized -> {note_result.status_code} ({note_duration:.3f}s)"
            )

        if output:
            output("Sending tools/list")
        tools_payload = {"jsonrpc": "2.0", "id": "tools-1", "method": "tools/list"}
        tools_duration, tools_result = await timed(
            "tools/list",
            post_rpc(client, endpoint, tools_payload, timeout),
            output=output,
        )
        if output:
            output(
                f"tools/list -> {tools_result.status_code} ({tools_duration:.3f}s)\n"
                f"{json.dumps(tools_result.payload, indent=2)}"
            )

        if output:
            output("Calling tools/call search")
        search_payload = {
            "jsonrpc": "2.0",
            "id": "search-1",
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"query": "connector compliance"},
            },
        }
        search_duration, search_result = await timed(
            "tools/call search",
            post_rpc(client, endpoint, search_payload, timeout),
            output=output,
        )
        if output:
            output(
                f"tools/call search -> {search_result.status_code} ({search_duration:.3f}s)\n"
                f"{json.dumps(search_result.payload, indent=2)}"
            )

    return {
        "endpoint": endpoint,
        "initialize": {"duration": init_duration, "result": init_result},
        "notifications_initialized": {"duration": note_duration, "result": note_result},
        "tools_list": {"duration": tools_duration, "result": tools_result},
        "search": {"duration": search_duration, "result": search_result},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe MCP streamable-http handshake like ChatGPT connector"
    )
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    asyncio.run(run_probe(args.server_url, args.timeout))


if __name__ == "__main__":
    main()

