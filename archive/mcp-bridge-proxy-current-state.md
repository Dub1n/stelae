# Stelae MCP Bridge/Proxy – Current State & Diagnosis Plan

## TL;DR

- **Public POST /mcp** intermittently returns **502/530 via Cloudflare**.
- **Local bridge** is up but throws an internal error in POST probing due to a bug in `build_envelopes()` (**`QueryParams.encode` AttributeError**), which derails health/scan logic and POST handling.
- **Bridge SSE fallback** incorrectly points to `/stream` (not served by proxy). The proxy exposes **`/<server>/sse`** (e.g., `/mem/sse`).
- **Upstream proxy** redirects POST `/mem` → **301 to `/mem/`**; bridge currently doesn’t follow POST redirects, and the upstream likely requires a specific **message envelope** (not raw JSON-RPC) for POST endpoints.
- Cloudflared is healthy but reports **origin refused** when the bridge restarts or crashes—symptom, not root cause.

---

## Environment Overview

- Process manager: **PM2**
- Services:
  - **mcp-proxy** (Go binary at `/home/gabri/apps/mcp-proxy/build/mcp-proxy`), listens on **`:9092`**, serves multiple SSE servers.
  - **mcp-bridge** (Python FastAPI + Uvicorn on **`:9090`**), exposes `/mcp` for SSE (GET) + JSON-RPC POST and various debug endpoints.
  - **cloudflared** tunnel publishes public domain **`https://mcp.infotopology.xyz`** → origin **`http://127.0.0.1:9090`**.
- Other PM2 apps observed: `strata`, `shell`, `memory`, `docs`, `1mcp`.

---

## What Works / Addressed Items

- **FastAPI ModuleNotFoundError fixed** by ensuring the bridge runs with the venv (`$HOME/.venvs/stelae-bridge` in PATH). Bridge binds to **:9090** and serves `/healthz`, `/version`, `/debug/*` at times.
- **Proxy manifest accessible** via `http://127.0.0.1:9092/.well-known/mcp/manifest.json`; lists SSE servers: `strata`, `fs`, `rg`, `sh`, `docs`, `mem`, `fetch` with URLs `https://mcp.infotopology.xyz/<name>/sse` (local base: `http://127.0.0.1:9092/<name>/sse`).
- **Proxy is active**: logs show each server connecting and “Handling requests at `/<name>/`”; also logs POST/GET hits on `/mem/` when we probed.

---

## Observed Failures (Current)

1. **Bridge internal error during POST probe**
   - Stack: `AttributeError: 'QueryParams' object has no attribute 'encode'` at `bridge/stream_http_bridge.py:82` (inside `build_envelopes()`), triggered by `/debug/scan`, `/healthz`, and POST initialization probing.
   - Effect: **500 Internal Server Error** for some bridge endpoints and **broken POST forwarding**.

2. **Wrong SSE fallback path**
   - Log: `WARNING: No upstream SSE path confirmed; falling back to /stream` → upstream returns **404** (the proxy does not serve `/stream`).
   - Proxy’s valid SSE endpoints are **`/<server>/sse`** (e.g., `/mem/sse`).

3. **Upstream POST routing/redirects**
   - Direct upstream probes show:
     - `POST /<server>` → **301** to `/<server>/` (docs/fetch/mem/rg/sh/strata).
     - `POST /<server>/message` → **400** (likely wrong envelope/headers).
     - `POST /<server>/` → **404** with raw JSON-RPC body.
   - Bridge passes through upstream 301 at times (public `POST /mcp` received **301** with `x-bridge-upstream-path: /mem`).

4. **Public errors via Cloudflare**
   - Earlier **530 (error code 1033)** and later **502** on `POST https://mcp.infotopology.xyz/mcp`.
   - Cloudflared logs concurrently show `Unable to reach the origin service: connect: connection refused 127.0.0.1:9090` (when bridge process down/crashing) and some `unexpected EOF`—consistent with bridge restarts or broken SSE.

5. **HEAD on SSE**
   - `HEAD https://mcp.infotopology.xyz/mem/sse` → **405** (Method Not Allowed). This is common for SSE endpoints; **GET** is the correct method for SSE.

---

## Likely Causes (ranked)

1. **Bridge envelope bug (high confidence)**
   - `httpx.QueryParams(...).encode()` is invalid. The bridge attempts to wrap the JSON-RPC payload in a form/body envelope (likely `data=...`). This throws before any probing/forwarding finishes.

2. **Bridge SSE fallback misconfigured (high)**
   - Falling back to `/stream` guarantees **404**. Should default to a known-good **`/mem/sse`** when probing is inconclusive (or, better, read from the proxy manifest).

3. **POST redirect handling (medium)**
   - Upstream returns **301** `/mem` → `/mem/`; if the bridge does not follow redirects for POST while preserving method/body, it will break initialization.

4. **Upstream expects a specific POST envelope (medium)**
   - 400 on `/message` hints at the upstream expecting a particular **message body shape** (e.g., `application/x-www-form-urlencoded` with `data=...`, or a wrapper JSON like `{data: "..."}`) rather than raw JSON-RPC.

5. **Cloudflared errors are secondary (medium)**
   - The tunnel is up; `connect: connection refused` arises when the bridge is not healthy or restarting; this will clear when the bridge is fixed.

6. **UDP buffer warnings (low)**
   - `failed to sufficiently increase receive buffer size` in cloudflared is a performance warning; not a functional blocker for HTTP/SSE here.

---

## Things We Can Safely Rule Out (so far)

- **DNS/TLS problems**: TLS handshakes succeed; cert chain OK; ALPN `h2` accepted.
- **Proxy totally down**: It’s running, advertises servers, logs incoming requests, and exposes `/<server>/sse`.
- **Cloudflare configuration as the root cause**: Errors correlate with origin unavailability/misrouting; CF is behaving as expected given origin failures.
- **Missing OpenAPI**: Not required for MCP; `openapi.json` failing is not germane.

---

## Minimal Fixes Recommended (not yet applied)

1. **Fix envelope encoding** in `build_envelopes()`
   - Use `urllib.parse.urlencode({"data": raw.decode()}).encode()` instead of `httpx.QueryParams(...).encode()`.
   - Ensure we don’t double-prepend `data=`.

2. **Enable POST redirect following**
   - Instantiate `httpx.AsyncClient(follow_redirects=True)` so `/mem` → `/mem/` keeps method/body.

3. **Correct SSE fallback**
   - Replace hard-coded fallback `/stream` with **`/mem/sse`** (or better: pick the first SSE URL from the manifest). This will make `GET /mcp` stream even if probing is inconclusive.

4. **(Optional) Auto-envelope heuristics**
   - If the upstream still 4xx’s on POST, try 2–3 envelope shapes in order (e.g., raw JSON, `application/x-www-form-urlencoded` `data=...`, `{ type:"jsonrpc", payload:... }`) and cache the first 2xx.

---

## Files to Inspect / Modify

- **Bridge**
  - `/home/gabri/dev/stelae/bridge/stream_http_bridge.py`
    - Functions: `build_envelopes()`, `probe_post_endpoint()`, `ensure_config()` (SSE path selection), POST forwarding, and debug endpoints.
    - Look for where `httpx.AsyncClient()` is created (add `follow_redirects=True`).
    - Locate the fallback literal `/stream` and swap to `/mem/sse` or manifest-derived path.
- **Proxy**
  - Repo at `\wsl.localhost\Ubuntu\home\gabri\apps\mcp-proxy` (binary: `/home/gabri/apps/mcp-proxy/build/mcp-proxy`).
  - Confirm HTTP routes for POST:
    - Which endpoints accept messages? (`/<server>/`, `/<server>/message`, or something else?)
    - Expected content-type/envelope for POST.
  - Logs already show: `Handling requests at /mem/` and requests hitting `/mem/`.
- **Config**
  - `/home/gabri/dev/stelae/config/proxy.json` – verify server names and base paths match manifest.
  - Cloudflared credentials at `~/.cloudflared/7a74f696-46b7-4573-b575-1ac25d038899.json` (no change needed unless ingress differs). If there’s a YAML, confirm it forwards `https://mcp.infotopology.xyz/*` → `http://127.0.0.1:9090/*`.
- **PM2**
  - Ensure `mcp-bridge` environment includes `VIRTUAL_ENV` and has `PATH` prefixed with `$VIRTUAL_ENV/bin` so FastAPI/uvicorn/httpx versions are consistent.

---

## Current Diagnostics Evidence (condensed)

- Proxy manifest lists SSE URLs: `https://mcp.infotopology.xyz/<server>/sse` for servers `strata, fs, rg, sh, docs, mem, fetch`.
- Upstream probes (localhost:9092):
  - `POST /<server>` → 301; `POST /<server>/` → 404 with raw JSON.
  - `POST /<server>/message` → 400 (envelope mismatch likely).
  - `GET /<server>/sse` expected to stream (HEAD often 405; that’s okay).
- Bridge logs:
  - Multiple `HEAD /mcp` 200 and `GET /mcp` 200, but POST `/mcp` mostly 503/502 due to probe errors.
  - Warning: `No upstream SSE path confirmed; falling back to /stream` → upstream 404.
  - Error: `AttributeError: 'QueryParams' object has no attribute 'encode'` during `debug_scan` → **500** on `/healthz`, `/version`, `/debug/*` at times.
- Cloudflared logs:
  - Repeated `Unable to reach the origin service ... 127.0.0.1:9090` while bridge is restarting/crashing.
  - Occasional QUIC warnings (non-blocking) and stream cancellations (expected under restarts).
- Public tests:
  - `HEAD/GET https://mcp.infotopology.xyz/mcp` sometimes 502; earlier a 301 pass-through from bridge showed `x-bridge-upstream-path: /mem`.

---

## Next-Session Plan (step-by-step)

1. **Patch bridge (tiny, surgical)**
   - Fix `build_envelopes()` encode.
   - Add `follow_redirects=True` to the `httpx.AsyncClient` used for upstream POSTs.
   - Change fallback SSE to `/mem/sse` (or read from manifest and pick the first SSE URL).
   - Restart `mcp-bridge` with venv PATH.
2. **Local verification**
   - `GET /healthz` → `{status: "ok"}`
   - `GET /version` → shows `upstream.postPath` set from probe; `routes` includes `/mcp (GET,HEAD,POST)`.
   - `GET /mcp` with `Accept: text/event-stream` → see at least keepalives or an initial `event: endpoint` line.
   - `POST /mcp` initialize → 2xx (or a clear upstream error); response should include `x-bridge-upstream-*` headers for transparency.
3. **Public verification**
   - Restart `cloudflared` (only if needed) and confirm `GET https://mcp.infotopology.xyz/mcp` streams.
   - `POST https://mcp.infotopology.xyz/mcp` initialize → 2xx.
4. **If POST still 4xx**
   - Implement auto-envelope fallback (try `application/x-www-form-urlencoded data=...`, raw JSON, and `{ type, payload }`). Log and cache the successful shape and upstream path.
5. **Stabilization**
   - Add structured logs: selected SSE path; selected POST path; envelope type; upstream status code; redirect chain if any.
   - Add `/debug/upstream` to dump cached selections and last errors (already partially present).

---

## Quality-of-Life Improvements (after green path)

- **Manifest-driven routing**: parse the proxy manifest at startup and prefer its SSE URLs instead of guessing.
- **Health surface**: expose `/healthz` to verify upstream SSE connectability (connect+read 1 line with timeout) and POST reachability (HEAD or minimal POST probe).
- **CORS & cache headers**: ensure `Cache-Control: no-store` and permissive CORS as required by the ChatGPT Connector.
- **Observability**: add `x-bridge-upstream-*` consistently on all proxied responses; include timing and selected envelope.
- **Graceful reloads**: handle SIGTERM/SIGINT to close SSE streams gracefully before PM2 restarts.

---

## Handy Commands (for the next session)

- **Manifest / servers**
  - `curl -s http://127.0.0.1:9092/.well-known/mcp/manifest.json | jq -C .`
  - `curl -s http://127.0.0.1:9092/.well-known/mcp/manifest.json | jq -r '.servers[].url'`
- **SSE checks**
  - `curl -N http://127.0.0.1:9092/mem/sse -H 'Accept: text/event-stream' | sed -n '1,5p'`
  - `curl -N http://127.0.0.1:9090/mcp -H 'Accept: text/event-stream' | sed -n '1,5p'`
- **POST probes**
  - Raw JSON-RPC: `curl -sk -X POST http://127.0.0.1:9092/mem/ -H 'Content-Type: application/json' --data '{...}' -i`
  - Form `data=`: `curl -sk -X POST http://127.0.0.1:9092/mem/ -H 'Content-Type: application/x-www-form-urlencoded' --data-urlencode "data={...}" -i`
- **Bridge debug**
  - `curl -s http://127.0.0.1:9090/healthz | jq .`
  - `curl -s http://127.0.0.1:9090/version | jq .`
  - `curl -s http://127.0.0.1:9090/debug/scan | jq -C` (after the encode fix)
- **Logs**
  - `pm2 logs mcp-bridge --lines 200`
  - `pm2 logs mcp-proxy --lines 200`
  - `pm2 logs cloudflared --lines 200`

---

## Open Questions

- Precisely which **POST endpoint + envelope** does `mcp-proxy` expect for each server? (`/<server>/`, `/<server>/message`, or a unified `/mcp`?) If unified, where is it wired?
- Should the bridge expose a **single `/mcp`** that multiplexes to a chosen default server (likely `mem`) or should it support **`/mcp/<server>`** for explicit routing? (The ChatGPT Connector prefers a single entry point, so defaulting to `mem` is fine.)
- Any **rate limits or auth** we need to consider at the proxy layer that could cause 400s?

---

## Appendix: Minimal Patch Sketch (reference)

- **Envelope fix** (Python):

  ```python
  # at top
  from urllib.parse import urlencode

  # inside build_envelopes()
  # replace the broken line with:
  form_bytes = urlencode({"data": raw.decode()}).encode()
  ```

- **Follow redirects**:

  ```python
  async with httpx.AsyncClient(follow_redirects=True, timeout=...) as client:
      ...
  ```

- **SSE fallback**: change hard-coded `"/stream"` to `"/mem/sse"` (or parse manifest and pick first `servers[].url`).
