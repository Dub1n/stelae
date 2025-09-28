#!/usr/bin/env python3
"""Minimal Streamable-HTTP probe to emulate ChatGPT connector handshake."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

DEFAULT_SERVER_URL = "https://mcp.infotopology.xyz/mcp"
DEFAULT_TIMEOUT = 20.0


def _event_stream_lines(text: str):
    # split by \n, keep simple
    for line in text.splitlines():
        yield line.rstrip("\r")


async def timed(name: str, coro) -> Tuple[float, Any]:
    start = time.perf_counter()
    result = await coro
    duration = time.perf_counter() - start
    print(f"[{name}] {duration:.3f}s")
    return duration, result


async def fetch_session_endpoint(client: httpx.AsyncClient, server_url: str, timeout: float) -> str:
    """Open the SSE facade and return the per-session endpoint"""
    headers = {"Accept": "text/event-stream"}
    async with client.stream("GET", server_url, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        event: Optional[str] = None
        data: Optional[str] = None
        async for chunk in resp.aiter_text():
            for line in _event_stream_lines(chunk):
                if line.startswith("event: "):
                    event = line[len("event: "):].strip()
                elif line.startswith("data: "):
                    data = line[len("data: "):].strip()
                elif line == "":
                    if event == "endpoint" and data:
                        return data
                    event = None
                    data = None
        raise RuntimeError("SSE stream closed without endpoint event")


@dataclass
class JsonRpcResult:
    status_code: int
    headers: Dict[str, str]
    payload: Dict[str, Any] | None


async def post_rpc(client: httpx.AsyncClient, endpoint: str, payload: Dict[str, Any], timeout: float) -> JsonRpcResult:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    resp = await client.post(endpoint, headers=headers, json=payload, timeout=timeout)
    text = resp.text.strip()
    parsed: Dict[str, Any] | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"_raw": text}
    return JsonRpcResult(status_code=resp.status_code, headers=dict(resp.headers), payload=parsed)


async def run_probe(server_url: str, timeout: float) -> None:
    async with httpx.AsyncClient(http2=True, timeout=timeout) as client:
        print(f"Opening SSE session at {server_url}")
        _, endpoint = await timed("sse-open", fetch_session_endpoint(client, server_url, timeout))
        print(f"Session endpoint: {endpoint}")

        initialize_payload = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "chatgpt-probe", "version": "0.1"},
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {}, "prompts": {}, "resources": {}, "tools": {}},
            },
        }

        print("Sending initialize")
        init_duration, init_result = await timed(
            "initialize",
            post_rpc(client, endpoint, initialize_payload, timeout),
        )
        print(f"initialize -> {init_result.status_code} ({init_duration:.3f}s)\n{json.dumps(init_result.payload, indent=2)}")

        print("Sending notifications/initialized")
        note_payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        note_duration, note_result = await timed(
            "notifications/initialized",
            post_rpc(client, endpoint, note_payload, timeout),
        )
        print(f"notifications/initialized -> {note_result.status_code} ({note_duration:.3f}s)")

        print("Sending tools/list")
        tools_payload = {"jsonrpc": "2.0", "id": "tools-1", "method": "tools/list"}
        tools_duration, tools_result = await timed(
            "tools/list",
            post_rpc(client, endpoint, tools_payload, timeout),
        )
        print(f"tools/list -> {tools_result.status_code} ({tools_duration:.3f}s)\n{json.dumps(tools_result.payload, indent=2)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe MCP streamable-http handshake like ChatGPT connector")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    asyncio.run(run_probe(args.server_url, args.timeout))


if __name__ == "__main__":
    main()
