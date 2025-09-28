# Stelae → ChatGPT Connector: Compliance Requirements Spec (v0.1‑draft)

> Purpose: define the *edge* contract our public endpoint must satisfy to be recognized by ChatGPT as a custom MCP connector, while cleanly brokering to our internal proxy/servers.

---

## 0) Scope & goals

- **Target client**: ChatGPT (custom connector, MCP-compatible).
- **Transport**: HTTPS (public) with **SSE (GET)** for liveness/notifications and **JSON‑RPC 2.0 (POST)** for requests/responses.
- **Intermediaries**: Cloudflare in front; `cloudflared` tunnel to local bridge → local MCP proxy/servers.
- **Non-goals**: authoring or constraining upstream servers; we only normalize the edge surface.

---

## 1) Public surface (MUST/SHOULD)

### 1.1 Discovery

- **MUST** serve MCP manifest at: `/.well-known/mcp/manifest.json` (public, GET).
  - **Content**: name/description; **servers** (SSE endpoints; see §1.3) and advertised tools/prompts/resources (mirrored or generated).
  - **Cache**: `Cache-Control: no-store` (or short TTL) during development.

### 1.2 Primary connector endpoint (single path)

- **Path**: `/mcp` on the public origin `https://<host>`.
- **Methods**:
  - **GET** → **SSE** stream (see §1.3).
  - **HEAD** → **200 OK** with the same headers as GET-SSE (no body). *This is used by clients for a quick capability probe.*
  - **POST** → **JSON‑RPC 2.0** request (see §1.4).
- **MUST NOT** issue **3xx redirects** for either GET/POST at this path. Respond directly (Cloudflare and standard HTTP clients won’t follow 301/302 for POST reliably).
- **Security**: HTTPS only; HTTP should be 301 to HTTPS at edge (Cloudflare).

### 1.3 SSE (Server-Sent Events) semantics (GET /mcp)

- **Response headers (MUST)**
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-store`
  - `Connection: keep-alive` (implicitly via HTTP/2; still safe to include)
  - `X-Accel-Buffering: no` (defensive; avoid proxy buffering)
- **Initial activity (SHOULD)**: send a first event or comment **within 3–5s** to open pipes through intermediaries. Either:
  - Comment heartbeat: a single line starting with `:` (e.g., `:\n\n`), or
  - `event: ping\n` + `data: {}\n\n`.
- **Keepalives (MUST)**: continue sending heartbeats at **≤20s** interval to prevent Cloudflare/clients from idling out the stream.
- **Event payloads (MAY)**: if server-initiated MCP notifications are needed, emit them as `event: message` with `data: <JSON-RPC notification>`. The connector itself **does not depend** on server-initiated events to function but must tolerate them.
- **Error handling**: if upstream becomes unavailable, keep the stream alive with heartbeats; only terminate on connector shutdown or explicit client disconnect.

### 1.4 JSON‑RPC over HTTP (POST /mcp)

- **Request**: body is a standard **JSON‑RPC 2.0** object (or batch array).
  - **Content-Type**: `application/json`.
  - **Size limits**: accept at least **5 MB** bodies (configurable) to accommodate tool arguments.
- **Handshake (MUST)**: support `initialize` request:

  ```json
  {"jsonrpc":"2.0","id":"<string|number>","method":"initialize","params":{"protocolVersion":"2024-11-05"}}
  ```

  - **Success** → `200 OK` with JSON‑RPC `result` describing server capabilities.
  - **Failure** (unsupported version) → return JSON‑RPC **error** (e.g., code **-32600** Invalid Request, or tool-specific code) with `200 OK` at HTTP layer. Avoid 4xx/5xx for protocol-level errors.
- **General calls**: treat POST bodies opaquely and forward to the appropriate upstream server/action. Return the upstream JSON‑RPC response verbatim.
- **Status codes**:
  - **200 OK** for all successful JSON‑RPC responses (including application-level errors encoded in JSON‑RPC `error`).
  - **4xx/5xx** reserved for transport faults (malformed JSON, auth failure at edge, upstream unreachable after retries). When used, return a **plain-text** body and **never** HTML.
- **Redirects**: **prohibited**. No `Location` responses from `/mcp`.
- **Timeouts**: client-visible request timeout ≥ **60s**; connector retries upstream with bounded backoff but returns promptly on hard failures.

### 1.5 Health + introspection (nice-to-have)

- **/healthz** → JSON `{status:"ok", ...}` reflecting downstream reachability.
- **/version** → JSON with bridge version, selected upstream, and protocol hint.
- **/debug/** → optional: `routes`, `scan`, `upstream` (authentication off by default; enable only for trusted IPs).

---

## 2) Behavior through Cloudflare (edge constraints)

- **SSE compatibility (MUST)**: ensure no buffering and regular heartbeats. Target heartbeat ≤20s.
- **Allowed methods**: GET/HEAD/POST for `/mcp` must be permitted. Block others.
- **No 530/502 from edge**: connector must surface 200 + JSON‑RPC error bodies rather than letting tunnel/origin failures bubble as 5xx from Cloudflare.
- **CORS**: not required for ChatGPT usage; if enabled, keep permissive or origin-scoped and avoid preflight on `/mcp`.

---

## 3) Upstream mapping model (internal to us)

- **Routing table**: bridge determines a single upstream **message endpoint** and an **SSE endpoint** from the manifest or heuristics, then *pins* them. Example upstreams discovered today:
  - SSE candidates like `/{server}/sse` (e.g., `/mem/sse`).
  - Message endpoints like `/{server}/message` or `/{server}/` (POST). Some servers return `400` if the envelope is wrong; we normalize the envelope at the bridge.
- **No redirects across upstreams**: normalize at the bridge; never forward 301/302 to the client.
- **Debug headers (SHOULD)**: add `X-Bridge-Upstream-URL`, `X-Bridge-Upstream-Path`, `X-Bridge-Upstream-Status` to POST responses for observability (strip at edge if desired).

---

## 4) Error model

- **Transport error → HTTP 5xx**:
  - Upstream down/unreachable after retry window.
  - Malformed JSON at transport (return `400 Bad Request`).
- **Protocol error → HTTP 200 + JSON-RPC `error`**:
  - Unknown method, bad params, unsupported `protocolVersion`.
- **SSE liveness**: if upstream SSE fails, maintain the public stream with heartbeats and simultaneously attempt background reconnects upstream; surface a `server-status` event (optional) to aid debugging.

---

## 5) Limits & performance

- **Concurrent SSE streams**: support ≥ **5** simultaneous client streams.
- **Concurrent POST**: sustain ≥ **50 RPS** burst with queueing backpressure; connection pooling to upstream.
- **Request body**: accept at least **5 MB**.
- **Response size**: stream large results incrementally when upstream supports it; otherwise buffer up to **10 MB**.

---

## 6) Security & privacy

- **TLS** end-to-end; HSTS recommended at Cloudflare.
- **Logging**: redact secrets within JSON‑RPC params in access logs.
- **Rate limiting**: basic per-IP limits at edge (e.g., 100 req/min) to protect origin.

---

## 7) Operational readiness

- **Observability**:
  - Access logs: method, path, status, latency, `cf-ray`, and (if present) `x-bridge-*`.
  - Health checks: local + remote.
- **Config knobs** (env/flags): upstream base URL, forced SSE path, forced POST path, heartbeat interval, request timeout, max body size, CORS toggle.
- **Zero-downtime deploy**: rolling restart of bridge; SSE streams allowed to drain.

---

## 8) Compatibility guidance (from client observations)

- ChatGPT **probes** `/mcp` with **HEAD** (expect 200), **GET (SSE)**, then **POST initialize**. Avoid redirecting POST requests (client did not follow 301 during tests).
- For `initialize` with `protocolVersion` like `"2024-11-05"`, return **200** + JSON‑RPC result; do **not** reply `202 Accepted`.

---

## 9) Open questions (to verify against official docs)

- Whether the client requires a specific **event name** on SSE (e.g., `event: endpoint`) vs. mere keepalives. Current plan: keepalives only; tolerate/forward notifications.
- Exact JSON shape of `initialize.result` that ChatGPT relies on (tools/prompts/resources lists vs. manifest-driven discovery). Our bridge will forward upstream results verbatim.
- Batch JSON‑RPC: does the client send batches? We **will** accept arrays and forward upstream.

---

## 10) Minimal acceptance tests

1) `HEAD /mcp` → 200 with `Content-Type: text/event-stream`.
2) `GET /mcp` → stream opens; heartbeats seen every ≤20s.
3) `POST /mcp` `initialize` → 200 + JSON-RPC result; includes advertised tools.
4) Random unknown method → 200 + JSON-RPC error.
5) Upstream killed → GET stream stays alive with heartbeats; POST returns 502 within timeout.
6) Cloudflare end-to-end: no 502/530/1033 from edge during normal operations.

---

## 11) Nice-to-have QoL (non-blocking)

- `/mcp` **OPTIONS** returns 204 with `Allow: GET, HEAD, POST`.
- `/mcp` **GET ?probe=1** returns 204 (no body) for cheap liveness checks (optional).
- `/metrics` (private) for Prometheus scraping.

---

## 12) Change log & ownership

- Owner: Stelae Infra.
- Version: v0.1‑draft. Mark deltas against this spec in PRs & deployment notes.
