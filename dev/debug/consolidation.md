Got it. Here’s a tight plan that covers both consolidation paths, plus a clear recommendation and concrete steps to get you to a **single URL** that Codex and other clients can use.

# Goal (common to both)

* One public/local **endpoint URL** (e.g. `http://127.0.0.1:9092/mcp` locally or `https://mcp.infotopology.xyz/mcp` remotely) that:

  * **GET** → serves **SSE** (`text/event-stream`) with keepalives.
  * **POST** → accepts **JSON-RPC 2.0** (e.g. `initialize`, `tools/*`), returning **2xx** on success with a JSON body.
* One authoritative manifest at `/.well-known/mcp/manifest.json`.
* All other service-specific routes remain **internal/private**.

---

# Recommendation

**Prefer Approach A: “Proxy-only facade”** (remove the FastAPI bridge).
It collapses a hop, eliminates the probing/autodetection that’s causing 30x/40x/50x noise, and puts all connector semantics in one place. That makes debugging way easier and production behavior more deterministic.

If you want a risk-reduced interim path while you’re still debugging upstreams, **Approach B (“Bridge owns the facade”)** is fine—then later flip to A.

---

# Approach A — Make `mcp-proxy` the ChatGPT-compliant facade

### A: High-level

Cloudflare (optional) → `mcp-proxy` (public `/mcp` for GET+POST) → internal SSE servers (`/mem/`, `/docs/`, `/sh/`, …).

### A: Required behavior (what to implement in the proxy)

1. **Manifest**

   * Serve `GET /.well-known/mcp/manifest.json` (static JSON) that lists your tools/resources and **does not** expose internal paths.
   * Keep only what the client needs (minimal and accurate).

2. **SSE**

   * `GET /mcp`
   * Response: `200`, header `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`.
   * Send an initial `event: endpoint` (optional but helpful), then periodic comments (`:\n`) or `event: ping` every ~15–30s.
   * **Internals:** pick one upstream SSE bus to multiplex (e.g., `mem/sse`) **or** run a fan-in that forwards relevant upstream events as `data:` lines. Keep it simple first: just keepalive + `endpoint` is enough for many clients.

3. **POST (JSON-RPC)**

   * `POST /mcp` with `Content-Type: application/json`
   * Accept a JSON-RPC 2.0 envelope and route it:

     * `initialize` → respond locally with supported protocol version, server info, etc. (no upstream needed).
     * Tool calls (`tools/*`) → dispatch to the appropriate internal server (mem/docs/sh/…) via your existing code.
   * **Status codes:** 2xx for valid JSON-RPC responses (even if method-level error → put it in JSON-RPC `error`), `400` for malformed JSON, `415` for wrong content-type, `404` for other paths, `405` for unsupported methods.

4. **Method discipline**

   * `/mcp`: allow **GET** + **POST** only.

     * `HEAD` → `200` (helpful for health checks).
     * Others → `405`.
   * Ensure **no 301/302** on `/mcp`. Return **exactly** `/mcp`.

5. **Health & version (local only)**

   * `GET /healthz` → `{status:"ok"}` independent of upstream.
   * `GET /version` → proxy version, upstream reachability summary.

6. **Logging & headers**

   * Add `X-Proxy-Upstream-Path`, `X-Proxy-Upstream-Status` when you do fan-out so debugging stays easy.
   * Request-id per call in logs.

### A: Concrete implementation steps

* In the `mcp-proxy` repo (`/home/gabri/apps/mcp-proxy` source clone):

  1. **Add a top-level HTTP router** (if you don’t already have one) that mounts:

     * `GET /.well-known/mcp/manifest.json` (serve a file or embed).
     * `GET /mcp` → SSE handler (simple ticker sending keepalives; optional minimal fan-in from `mem/sse` later).
     * `POST /mcp` → JSON-RPC handler (decode, route, respond).
     * `GET /healthz`, `GET /version`.
  2. **JSON-RPC handler**:

     * Handle `initialize` locally (return protocol `2024-11-05` and a basic capabilities block).
     * For tool methods, map method → internal server (`/mem/`, `/docs/`, etc.) and reuse your existing internal client.
  3. **Remove external probing**; delete/disable any “autodetect upstream path” logic. The public facade is **fixed**.
  4. **Keep existing SSE buses** under **internal** paths (`/mem/sse`, `/docs/sse`…), but don’t expose them publicly if not needed.
  5. **Build & run** under PM2 in place of the bridge on the public port (or keep current port and switch Cloudflare to it).

### A: Acceptance checklist (local)

* `curl -sI http://127.0.0.1:9092/mcp` → `200` and **no redirect**.
* `curl -N http://127.0.0.1:9092/mcp -H 'Accept: text/event-stream'` → initial line(s) + keepalives.
* `curl -s -X POST http://127.0.0.1:9092/mcp -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05"}}'` → `200` JSON with result (no 30x/40x/50x).
* `curl -s http://127.0.0.1:9092/.well-known/mcp/manifest.json` → valid JSON, minimal, accurate.

---

# Approach B — Keep the FastAPI bridge as the facade (proxy becomes internal)

### B: High-level

Cloudflare → **FastAPI bridge** (public `/mcp`) → **mcp-proxy** (internal only) → tool servers.

### B: What to change (Bridge)

* **Delete probing** and **hardcode**:

  * Upstream base: `http://127.0.0.1:9092`
  * SSE target: choose **one** (e.g., `http://127.0.0.1:9092/mem/sse`) or keepalive-only SSE.
  * POST target mapping:

    * `initialize` handled in-bridge.
    * Tool methods forwarded to **fixed** internal endpoints (no 301 hunting).
* **Fix the envelope builder bug** (`QueryParams.encode` doesn’t exist): use `urllib.parse.urlencode` or just `json.dumps(payload)` with proper content-type.
* **Ensure**:

  * `GET /mcp` → SSE with keepalives.
  * `POST /mcp` → JSON-RPC; return **2xx** on valid JSON-RPC responses.
  * No redirects on `/mcp`.
  * Manifest is served by the **bridge**.

### What to change (Proxy)

* Treat `mcp-proxy` as **internal** only:

  * Keep `/mem/`, `/docs/`, `/sh/`, `/fetch/`, `/rg/`, `/fs/` routes.
  * Drop any public-facing manifests or public SSE if not needed.
  * No need to be ChatGPT-compliant.

### B: Acceptance checklist (local)

Same as Approach A, but hit the bridge port (`:9090`).

---

# “Squish now or later?”

* **Squish now (my recommendation):** Do it **before** the deeper debugging. Collapsing the autodetection and setting a single, fixed public `/mcp` will remove an entire class of 301/404/405/Cloudflare error debugging. It’s mostly routing + handler plumbing, not risky logic.
* If you’re time-constrained, start with **Approach B** (fewer code changes), pass the acceptance checks, then move to **Approach A** when you’re comfortable.

---

# Minimal task list to action (choose A or B)

### If **Approach A** (proxy-only facade)

1. In `mcp-proxy`:

   * Add `/.well-known/mcp/manifest.json` (static).
   * Implement `GET /mcp` SSE (keepalive ticker).
   * Implement `POST /mcp` JSON-RPC (`initialize` local; tools → internal).
   * Add `/healthz`, `/version`.
   * Remove any public redirects and probing.
2. PM2: run `mcp-proxy` on **public** port (where bridge currently is) or update Cloudflare to point at proxy.
3. Tests: run the acceptance checklist locally, then through Cloudflare.

### If **Approach B** (bridge facade)

1. In the **bridge**:

   * Remove probes; hardcode upstreams (proxy base, one SSE path).
   * Fix the `QueryParams.encode` bug in POST envelopes.
   * Ensure `/mcp` GET/POST correctness (no redirects, proper codes).
   * Serve the manifest.
2. Make `mcp-proxy` **internal-only** (no public exposure).
3. Tests: acceptance checklist on `:9090`, then through Cloudflare.

---

# One-URL client config

* **Local**: point Codex/clients to `http://127.0.0.1:<PORT>/mcp` (same URL for GET SSE and POST RPC).
* **Remote**: `https://mcp.infotopology.xyz/mcp`.
* That’s it—no more separate SSE vs POST URLs.

If you want, I can draft the actual code stubs for the `/mcp` GET (SSE) and `/mcp` POST (JSON-RPC) handlers for either Go (proxy) or Python (bridge), plus a minimal manifest JSON.
