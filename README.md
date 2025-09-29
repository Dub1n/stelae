# Stelae MCP Stack

A WSL-native deployment of [mcp-proxy](https://github.com/TBXark/mcp-proxy) that exposes your local Phoenix workspace to ChatGPT (and other MCP-aware agents) through a single HTTP/SSE endpoint. Everything runs on WSL, with an optional Cloudflare named tunnel for remote access.

---

## Stack Snapshot

| Component | Transport | Launch Command | Purpose |
|-----------|-----------|----------------|---------|
| mcp-proxy | HTTP/SSE (:9090) | `${PROXY_BIN}` | Aggregates tools/prompts/resources from local MCP servers into one endpoint. |
| Filesystem MCP | stdio | `${FILESYSTEM_BIN} --root ${STELAE_DIR}` | Scoped read/write access to the repo. |
| ripgrep MCP | stdio | `${RG_BIN} --stdio --root ${SEARCH_ROOT}` | Code search backend powering the `grep` tool. |
| Terminal Controller MCP | stdio | `${SHELL_BIN}` | Allowlisted command execution in Phoenix workspace. |
| Docy MCP | stdio | `${DOCY_BIN} --stdio` | Documentation / URL ingestion (feeds canonical `fetch`). |
| Basic Memory MCP | stdio | `${MEMORY_BIN}` | Persistent project memory. |
| Strata MCP | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing. |
| Fetch MCP | HTTP | `${LOCAL_BIN}/mcp-server-fetch` | Official MCP providing canonical `fetch`. |
| FastMCP bridge | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Exposes the full proxy catalog to desktop agents; falls back to local search/fetch if the proxy is unavailable. |
| 1mcp agent | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovery/promotion sidecar for capability lookups *(not yet implemented in this stack)*. |

Path placeholders expand from `.env`; see setup below.

---

## Prerequisites

- Windows 11 + WSL2 (Ubuntu) with systemd enabled (`/etc/wsl.conf` → `[boot]` / `systemd=true`).
- Tooling installed: Go, Node.js + npm (via NVM), `pm2`, Python 3.11+, `pipx`, `ripgrep`, `cloudflared`.
- Discovery agent *(planned)*: `npm install -g @1mcp/agent` (provides the `1mcp` binary; integration TBD).
- Cloudflare named tunnel `stelae` with DNS `mcp.infotopology.xyz` and credentials stored under `~/.cloudflared/`.

---

## Environment & Config

1. Copy `.env.example` → `.env` and update absolute paths:
   - Project roots: `STELAE_DIR`, `APPS_DIR`, `PHOENIX_ROOT`, `SEARCH_ROOT`.
   - Binaries: `FILESYSTEM_BIN`, `RG_BIN`, `SHELL_BIN`, `DOCY_BIN`, `MEMORY_BIN`, `STRATA_BIN`, `ONE_MCP_BIN`, `LOCAL_BIN/mcp-server-fetch`.
   - Public URLs: `PUBLIC_BASE_URL=https://mcp.infotopology.xyz`, `PUBLIC_SSE_URL=${PUBLIC_BASE_URL}/stream`.
2. Regenerate runtime config:
   \```bash
   make render-proxy
   \```
   This renders `config/proxy.json` from `config/proxy.template.json` using `.env` (with `.env.example` as fallback).
3. (Optional) Tailor tool annotations with `config/tool_overrides.json`. The file includes per-server read-only hints but leaves the `master` block empty so overrides are opt-in. Extend it per downstream server, or globally via the `master` section:
   ```json
   {
     "servers": {
       "fs": {
         "enabled": true,
         "tools": {
           "read_file": {
         "enabled": true,
         "annotations": {}
           }
         }
       },
       "fetch": {
         "enabled": true,
         "tools": {
           "fetch": {
             "enabled": true,
             "annotations": { "openWorldHint": true }
           }
         }
       }
     },
     "master": {
       "enabled": true,
       "tools": {
         "*": {
         "enabled": true,
         "annotations": {}
         }
       }
     }
   }
  ```
   The optional `master` block lets you override tools regardless of which server registered them; use `"*"` to target every tool, or list specific names. Setting `"enabled": false` at the server or tool level hides those entries from the manifest, `initialize`, and `tools/list` responses (and therefore from remote clients). Only the hints you specify are changed; unspecified hints keep the proxy defaults.
4. Ensure the FastMCP bridge virtualenv (`.venv/` by default) includes `mcp`, `fastmcp`, `anyio`, and `httpx`:
   \```bash
   .venv/bin/python -m pip install --upgrade mcp fastmcp anyio httpx
   \```
   Install the fetch server with `pipx install mcp-server-fetch` if not already present.

---

## Running the Stack (PM2)

`pm2` lives in your NVM install. Always source NVM before using it:

\```bash
source ~/.nvm/nvm.sh
\```

- Start + persist services:
  \```bash
  make up
  pm2 startup systemd    # run once; executes printed sudo command
  \```
- Apply config changes:
  \```bash
  make render-proxy            # re-renders config + propagates override path
  source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
  \```
- Check status / logs:
  \```bash
  source ~/.nvm/nvm.sh && pm2 status
  source ~/.nvm/nvm.sh && pm2 logs --lines 50
  \```
- Stop everything:
  \```bash
  make down
  \```

The helper script `scripts/restart_stelae.sh --full` wraps the full cycle (rebuild proxy, render config, restart PM2 fleet, redeploy Cloudflare worker, republish manifest) and is the fastest way to validate override changes end-to-end.

Logs default to `~/dev/stelae/logs/` (see `ecosystem.config.js`).

---

## Cloudflare Named Tunnel

`~/.cloudflared/config.yml`:

\```yaml
tunnel: stelae
credentials-file: ~/.cloudflared/7a74f696-46b7-4573-b575-1ac25d038899.json

ingress:

- hostname: mcp.infotopology.xyz
    service: http://localhost:9090
- service: http_status:404
\```

Operational steps:

1. Confirm DNS route:
   \```bash
   cloudflared tunnel route dns stelae mcp.infotopology.xyz
   \```
2. Manage via PM2:
   \```bash
   source ~/.nvm/nvm.sh && pm2 start "cloudflared tunnel run stelae" --name cloudflared
   source ~/.nvm/nvm.sh && pm2 save
   \```
3. After updating `.env` or proxy config, restart:
   \```bash
   make render-proxy
  source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
  source ~/.nvm/nvm.sh && pm2 restart cloudflared
   \```
4. Validate endpoints:
   \```bash
   curl -s http://localhost:9090/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -skI https://mcp.infotopology.xyz/stream
   \```

---

## Local vs Remote Consumers

- Remote agents (e.g. ChatGPT) use the public manifest served via Cloudflare, which now mirrors the complete downstream tool catalog (annotations included).
- Local MCP clients can connect to `http://localhost:9090` and receive the same tool metadata, so overrides remain consistent between environments.

---

## Future Developments

- Wire in the optional 1mcp discovery agent once the upstream contract settles *(not yet implemented)*.
- Decide whether to fully retire the legacy `scripts/stelae_search_mcp.py` shim now that the bridge mirrors the full catalog (track in TODO).

## Validation Checklist

1. `curl -s http://localhost:9090/.well-known/mcp/manifest.json | jq '{tools: (.tools | map(.name))}'` shows the full downstream catalog (filesystem, ripgrep, shell, docs, memory, strata, fetch, etc.).
2. From ChatGPT, exercise `fetch` (canonical) and `rg/search` (ripgrep) to confirm both return JSON payloads.
3. `pm2 status` shows `online` for proxy, the FastMCP bridge, each MCP, and `cloudflared`.

---

## Connector Readiness

- **Cloudflare tunnel up:** `pm2 start "cloudflared tunnel run stelae" --name cloudflared` (or `pm2 restart cloudflared`). `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` must return HTTP 200; a Cloudflare 1033 error indicates the tunnel is down.
- **Manifest sanity:** `curl -s http://localhost:9090/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'` verifies every essential MCP (filesystem, ripgrep, shell, docs, memory, fetch, strata, 1mcp).
- **SSE probes:** use the Python harness under `docs/openai-mcp.md` (or the snippets in this README) to connect to `/rg/sse` and `/fetch/sse`. Confirm `grep` returns results and `fetch` succeeds when `raw: true` (Docy’s markdown extraction still needs a fix; track in TODO).
- **Streamable HTTP bridge:** `scripts/stelae_streamable_mcp.py` now proxies the full catalog for local desktop agents; ensure the `stelae-bridge` pm2 process stays online.

```python
# Minimal SSE smoke test (run inside the stelae-search virtualenv)
import anyio, json
import httpx
from anyio import create_memory_object_stream
from httpx_sse import EventSource
from urllib.parse import urlparse
from mcp.client.session import ClientSession
from mcp.client.sse import SessionMessage
from mcp import types

async def smoke_rg():
    url = "http://localhost:9090/rg/sse"
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=30)) as client:
        async with client.stream("GET", url, headers={"Accept": "text/event-stream", "Cache-Control": "no-store"}) as response:
            response.raise_for_status()
            event_source = EventSource(response)
            base = urlparse(url)

            endpoint_ready = anyio.Event()
            endpoint_url = {"value": None}
            read_writer, read_stream = create_memory_object_stream(0)
            write_stream, write_reader = create_memory_object_stream(0)

            async with anyio.create_task_group() as tg:
                async def reader():
                    async for sse in event_source.aiter_sse():
                        if sse.event == "endpoint":
                            target = urlparse(sse.data.strip())._replace(scheme=base.scheme, netloc=base.netloc).geturl()
                            endpoint_url["value"] = target
                            endpoint_ready.set()
                        elif sse.event == "message":
                            message = types.JSONRPCMessage.model_validate_json(sse.data)
                            await read_writer.send(SessionMessage(message))
                    await read_writer.aclose()

                async def writer():
                    await endpoint_ready.wait()
                    async with write_reader:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=30)) as poster:
                            async for msg in write_reader:
                                await poster.post(
                                    endpoint_url["value"],
                                    json=msg.message.model_dump(by_alias=True, mode="json", exclude_none=True),
                                )

                tg.start_soon(reader)
                tg.start_soon(writer)

                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "grep",
                        {"pattern": "Stelae", "paths": ["/home/gabri/dev/stelae"], "max_count": 3, "recursive": True},
                    )
                    print(json.loads(result.content[0].text))
                    tg.cancel_scope.cancel()

anyio.run(smoke_rg)
```

---

## Maintenance

| Cadence | Action |
|---------|--------|
| Monthly | `git pull` + rebuild `mcp-proxy`; `pipx upgrade --include-apps`; `npm update -g`; redeploy via `make render-proxy` and restart services. |
| Quarterly | Audit filesystem roots, shell allowlist, Cloudflare credentials, and `.env` paths. |
| As needed | Update `.env` when binaries move; rerun `make render-proxy`; `pm2 restart mcp-proxy --update-env`. |

Keep a backup of `config/proxy.json` (or rely on git history) before large changes.

---

## Troubleshooting

- `pm2 status` shows `Permission denied` → source NVM first (`source ~/.nvm/nvm.sh`).
- `search` missing in manifest → verify the bridge virtualenv has the required Python deps and restart the `stelae-bridge` pm2 process (`source ~/.nvm/nvm.sh && pm2 restart stelae-bridge`).
- `fetch` missing → ensure `mcp-server-fetch` lives under `${LOCAL_BIN}` and is executable.
- `jq: parse error` → wrap the jq program in single quotes: `jq '{servers, tools: (.tools | length)}'`.
- Cloudflare 404 on `/stream` → proxy offline or tunnel disconnected; inspect `pm2 logs mcp-proxy` and `pm2 logs cloudflared`.

---

## Related Files

- `config/proxy.template.json` — template rendered into `config/proxy.json`.
- `scripts/render_proxy_config.py` — templating helper.
- `scripts/stelae_streamable_mcp.py` — FastMCP bridge that mirrors the proxy catalog for local clients.
- `scripts/stelae_search_mcp.py` — Legacy search shim kept for historical reference.
- `scripts/stelae_search_fetch.py` — HTTP shim (unused currently; keep for potential automation).
- `dev/server-setup-commands.md` — Cloudflare tunnel quick commands.
- `TODO.md` — backlog and future enhancements.
