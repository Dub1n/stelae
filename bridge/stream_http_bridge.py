#!/usr/bin/env python3
"""
Streamable HTTP bridge for MCP (no upstream SSE required).

- GET  /mcp     -> opens SSE stream; sets session cookie; sends one-time
                   synthetic `event: endpoint` pointing clients to this bridge's
                   public /mcp; emits periodic keepalives so Cloudflare won't
                   idle the connection.
- HEAD /mcp     -> 200 + text/event-stream headers
- POST /mcp     -> forwards JSON-RPC to a fixed upstream POST endpoint
                   (default /mcp on UPSTREAM_BASE). No need to pre-open GET.
- GET  /healthz -> liveness + quick upstream manifest reachability check
- GET  /version -> bridge metadata


# logger for bridge diagnostics
logger = logging.getLogger("bridge")
logger.setLevel(logging.INFO)
Everything else proxies to upstream (on :9092 by default).
"""

import os
import uuid
import asyncio
import sys
import time
from typing import Dict
from urllib.parse import urljoin

import httpx
from starlette.applications import Starlette
from starlette.responses import StreamingResponse, JSONResponse, Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware

BRIDGE_VERSION = "stelae-bridge/0.3.1-nostream"

UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "http://127.0.0.1:9092")
# Where to POST JSON-RPC upstream (fixed path; no upstream SSE dependency)
UPSTREAM_POST_PATH = os.environ.get("UPSTREAM_POST_PATH", "/mcp")
UPSTREAM_POST_URL = urljoin(UPSTREAM_BASE, UPSTREAM_POST_PATH.lstrip("/"))
# Optional: if your upstream manifest is somewhere else, override here
UPSTREAM_MANIFEST = os.environ.get("UPSTREAM_MANIFEST", urljoin(UPSTREAM_BASE, "/.well-known/mcp/manifest.json"))

# Public URL that clients should ultimately target (for the endpoint hint)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://mcp.infotopology.xyz")
PUBLIC_POST_URL = urljoin(PUBLIC_BASE_URL, "/mcp")

SESSION_COOKIE = "mcp_session"

# sid -> known/usable upstream POST endpoint (we just store the fixed one)
SESSION_ENDPOINTS: Dict[str, str] = {}

KEEPALIVE_INTERVAL = float(os.environ.get("KEEPALIVE_INTERVAL", "10"))  # seconds

# ---------- helpers ----------

async def ensure_session_ready(sid: str) -> bool:
    """
    In 'no upstream stream' mode, there's nothing to wait for. We just record
    the fixed upstream POST endpoint for this session.
    """
    if SESSION_ENDPOINTS.get(sid):
        return True
    SESSION_ENDPOINTS[sid] = UPSTREAM_POST_URL
    return True

# ---------- routes ----------

async def sse_head(_: Request) -> Response:
    return Response(
        status_code=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

async def sse_bridge(request: Request) -> Response:
    sid = request.cookies.get(SESSION_COOKIE) or uuid.uuid4().hex
    # mark this session as ready (fixed upstream endpoint)
    await ensure_session_ready(sid)

    headers = {
        "Cache-Control": "no-store",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "X-Content-Type-Options": "nosniff",
    }

    async def event_stream():
        # Immediately tell the client where to POST (synthetic 'endpoint')
        yield b"event: endpoint\n"
        yield f"data: {PUBLIC_POST_URL}\n\n".encode("utf-8")

        # Then keep the connection alive for CF/clients
        try:
            while True:
                # SSE comment line (ignored by clients, keeps the pipe open)
                yield b": keepalive\n\n"
                await asyncio.sleep(KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            return

    resp = StreamingResponse(event_stream(), headers=headers)
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=sid,
        path="/",
        secure=True,         # served via CF
        httponly=False,      # readable by client code if needed
        samesite="none",
    )
    return resp

async def post_mcp(request: Request) -> Response:
    # accept only JSON
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    # establish-session (a no-op here other than recording the upstream URL)
    sid = request.cookies.get(SESSION_COOKIE) or request.headers.get("MCP-Session") or uuid.uuid4().hex
    await ensure_session_ready(sid)

    endpoint = SESSION_ENDPOINTS.get(sid, UPSTREAM_POST_URL)

    # forward to upstream fixed endpoint
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=30)) as client:
        try:
            r = await client.post(endpoint, json=payload)
        except Exception as e:
            return JSONResponse({"error": f"upstream post failed: {e}"}, status_code=502)

    # Proxy back error bodies to help debugging; otherwise accept
    if r.status_code >= 400:
        # Try to pass through JSON if present; otherwise text
        body_text = r.text
        return JSONResponse({"upstream": r.status_code, "body": body_text}, status_code=502)
    return Response(status_code=202)

async def healthz(_: Request) -> Response:
    """Liveness + quick upstream manifest reachability (500ms)."""
    started = time.time()
    upstream_ok = False
    upstream_status = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(0.5, read=0.5)) as client:
            resp = await client.get(UPSTREAM_MANIFEST, headers={"Accept": "application/json"})
            upstream_status = resp.status_code
            upstream_ok = resp.status_code == 200
    except Exception:
        upstream_ok = False
    payload = {
        "status": "ok",
        "bridge": BRIDGE_VERSION,
        "elapsed_ms": int((time.time() - started) * 1000),
        "upstream": {
            "base": UPSTREAM_BASE,
            "manifest": UPSTREAM_MANIFEST,
            "reachable": upstream_ok,
            "status": upstream_status,
        },
    }
    return JSONResponse(payload, status_code=200)

async def version(_: Request) -> Response:
    info = {
        "bridge": BRIDGE_VERSION,
        "python": sys.version.split()[0],
        "upstreamBaseURL": UPSTREAM_BASE,
        "publicBaseURL": PUBLIC_BASE_URL,
        "protocolHint": "2024-11-05",
        "routes": ["/mcp (GET,HEAD,POST)", "/healthz", "/version"],
        "mode": "fixed-upstream-post",
        "upstreamPostPath": UPSTREAM_POST_PATH,
    }
    return JSONResponse(info, status_code=200)

async def reverse_proxy(request: Request) -> Response:
    target = urljoin(UPSTREAM_BASE, request.url.path)
    if request.url.query:
        target = f"{target}?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    method = request.method.upper()

    async with httpx.AsyncClient(timeout=httpx.Timeout(None, read=None)) as client:
        if method in {"GET", "HEAD"}:
            try:
                async with client.stream(method, target, headers=headers) as resp:
                    return StreamingResponse(
                        resp.aiter_raw(),
                        status_code=resp.status_code,
                        headers={k: v for k, v in resp.headers.items() if k.lower() != "transfer-encoding"},
                    )
            except httpx.HTTPError as e:
                return PlainTextResponse(str(e), status_code=502)
        else:
            body = await request.body()
            try:
                async with client.stream(method, target, headers=headers, content=body) as resp:
                    data = await resp.aread()
                    return Response(
                        content=data,
                        status_code=resp.status_code,
                        headers={k: v for k, v in resp.headers.items() if k.lower() != "transfer-encoding"},
                    )
            except httpx.HTTPError as e:
                return PlainTextResponse(str(e), status_code=502)

routes = [
    Route("/mcp", sse_head, methods=["HEAD"]),
    Route("/mcp", sse_bridge, methods=["GET"]),
    Route("/mcp", post_mcp, methods=["POST"]),
    Route("/healthz", healthz, methods=["GET"]),
    Route("/version", version, methods=["GET"]),
    Route(
        "/{path:path}",
        reverse_proxy,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    ),
]
app = Starlette(routes=routes)

# relaxed CORS during bring-up (tighten later if you want)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)
