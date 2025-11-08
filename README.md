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
| Docy manager MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/docy_manager_server.py` | Adds/removes Docy documentation sources via MCP/CLI, rendering `.docy.urls`. |
| Stelae integrator MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/stelae_integrator_server.py` | Consumes 1mcp discovery output, updates templates/overrides, and restarts the stack via `manage_stelae`. |
| Basic Memory MCP | stdio | `${MEMORY_BIN}` | Persistent project memory. |
| Strata MCP | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing. |
| Fetch MCP | HTTP | `${LOCAL_BIN}/mcp-server-fetch` | Official MCP providing canonical `fetch`. |
| Scrapling MCP | stdio | `uvx scrapling-fetch-mcp --stdio` | Scrapling fetcher (basic/stealth/max-stealth), adapted by the Go proxy at call time. |
| FastMCP bridge | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Exposes the full proxy catalog to desktop agents; falls back to local search/fetch if the proxy is unavailable. |
| 1mcp agent | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovers nearby MCP servers and writes `config/discovered_servers.json` for the integrator. |
| Custom tools MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/custom_tools_server.py` | Config-driven wrapper that exposes scripts listed in `config/custom_tools.json`. |

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
3. (Optional) Tailor tool metadata with `config/tool_overrides.json`. The file now supports per-tool `description`, aliasing via `name`, richer annotation fields (including `title`), plus full `inputSchema`/`outputSchema` overrides so manifests always describe the wrapped payloads we return. Extend it per downstream server, or globally via the `master` section:
   ```json
   {
     "servers": {
       "fs": {
         "enabled": true,
         "tools": {
          "read_file": {
            "enabled": true,
            "name": "fs_read_file",
            "description": "Read a file from the workspace without mutating it.",
            "annotations": {
              "title": "Read File",
              "readOnlyHint": true
            },
            "outputSchema": {
              "type": "object",
              "properties": {
                "result": {"type": "string"}
              },
              "required": ["result"]
            }
          }
         }
       },
       "fetch": {
         "enabled": true,
         "tools": {
           "fetch": {
             "enabled": true,
            "description": "Fetch a cached document by id via the sandboxed fetch server.",
            "annotations": {
              "title": "Fetch URL",
              "openWorldHint": true
            }
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
   The optional `master` block lets you override tools regardless of which server registered them; use `"*"` to target every tool, or list specific names. Setting `"enabled": false` at the server or tool level hides those entries from the manifest, `initialize`, and `tools/list` responses (and therefore from remote clients). Only the hints you specify are changed; unspecified hints keep the proxy defaults. Master-level renames are rejected on startup, and master-level description/title overrides emit a warning so you know global copy was applied.

   Aliases defined via `name` automatically flow through manifests, `initialize`, `tools/list`, and `tools/call`. Client requests using the alias are resolved back to the original downstream tool, while the original name remains available as a fallback for compatibility.
4. Proxy call-path adapter keeps flaky MCP servers usable without touching upstream code:
   - The Go proxy adapts tool call results at response time. Chain: pass-through → declared (uses `config/tool_overrides.json` outputSchema and inline heuristics when the declared schema implies it) → generic `{ "result": "..." }`.
   - On success, the proxy updates `config/tool_overrides.json` atomically when the used schema differs (e.g., persists generic when no declared exists). It tracks runtime state in `config/tool_schema_status.json` (path set via `manifest.toolSchemaStatusPath`).
   - This works for both stdio and HTTP servers and avoids inserting per-server shims.
4. Prime new servers’ schemas by running `python3 scripts/populate_tool_overrides.py` (optionally `--servers fs rg` to scope). This script launches each stdio MCP client, captures its advertised `inputSchema`/`outputSchema`, and fills any missing entries in `config/tool_overrides.json` without touching existing overrides.

5. Ensure the FastMCP bridge virtualenv (`.venv/` by default) includes `mcp`, `fastmcp`, `anyio`, and `httpx`:
   \```bash
   .venv/bin/python -m pip install --upgrade mcp fastmcp anyio httpx
   \```
   Install the fetch server with `pipx install mcp-server-fetch` if not already present.

   Install Scrapling MCP (optional, needed for high-protection sites):
   \```bash
   uv tool install scrapling-fetch-mcp
   uvx --from scrapling-fetch-mcp scrapling install
   \```

### Custom Script Tools

- `scripts/custom_tools_server.py` loads `config/custom_tools.json` (override with `STELAE_CUSTOM_TOOLS_CONFIG`) and registers each entry as part of the `custom` stdio server now declared in `config/proxy.template.json`.
- Every tool definition can include `name`, `description`, `command`, optional `args`, `cwd`, `env`, `timeout`, and `inputMode` (`json` to send arguments on stdin/`STELAE_TOOL_ARGS`, or `none` for fire-and-forget scripts).
- Sample config:
  ```json
  {
    "tools": [
      {
        "name": "sync_assets",
        "description": "Run the asset sync helper with JSON arguments.",
        "command": "./scripts/sync_assets.sh",
        "cwd": "${STELAE_DIR}",
        "timeout": 120,
        "inputMode": "json"
      }
    ]
  }
  ```
- After editing `config/custom_tools.json`, rerun `make render-proxy` and restart the proxy via PM2 so the manifest reflects the new tools.
- Legacy connector-only fallbacks (`search`, `fetch`) are disabled through `config/tool_overrides.json`, keeping the catalog limited to real servers and your custom scripts.

### Docy Source Catalog

- `config/docy_sources.json` is the canonical list of documentation URLs. Each entry can carry `id`, `url`, `title`, `tags`, `notes`, `enabled`, and `refresh_hours` metadata so we can track provenance in git.
- `scripts/render_docy_sources.py` converts the catalog into `.docy.urls`, which Docy reads live on every request (no restart needed). The renderer writes comments next to each URL so operators know not to edit the generated file manually.
- The dedicated Docy manager MCP server (`scripts/docy_manager_server.py`) exposes the `manage_docy` tool. Operations cover `list_sources`, `add_source`, `remove_source`, and `sync_catalog`, mirroring the CLI mode (`python scripts/docy_manager_server.py --cli --operation add_source --params '{"url": "https://docs.crawl4ai.com/"}'`).
- Set `STELAE_DOCY_CATALOG` / `STELAE_DOCY_URL_FILE` if you relocate the catalog; otherwise defaults are `config/docy_sources.json` and `.docy.urls` at the repo root.

### Bootstrapping the 1mcp catalogue

- Run `python scripts/bootstrap_one_mcp.py` after cloning this repo. The helper will:
  - clone or update `stelae-1mcpserver` under `${ONE_MCP_DIR:-~/apps/vendor/1mcpserver}`;
  - run `uv sync` inside the vendored repo (skip with `--skip-sync` if you manage deps elsewhere);
  - ensure `config/discovered_servers.json` exists so discovery output can be tracked in git;
  - write `~/.config/1mcp/mcp.json` (override via `--config`) with a ready-to-use `one_mcp` stdio stanza pointing at `ONE_MCP_BIN` and the vendored repo path.
- Sample CLI config generated by the script:
  ```json
  {
    "mcpServers": {
      "one_mcp": {
        "command": "/home/gabri/.local/bin/uv",
        "args": [
          "--directory",
          "/home/gabri/apps/vendor/1mcpserver",
          "run",
          "server.py",
          "--local"
        ]
      }
    },
    "discovery": {
      "cachePath": "/home/gabri/dev/stelae/config/discovered_servers.json"
    }
  }
  ```
- Re-run the bootstrap script any time you relocate the repo or want to refresh the CLI config; use `--skip-update`/`--skip-sync` if you only need to rewrite the config file.

### Installing servers discovered by 1mcp

- 1mcp writes its discovery payload to `config/discovered_servers.json` (array of `{name, transport, command|url, args, env, description, source, tools, requiresAuth, options}` objects). Keep the file in git so you can review pending server additions.
- The `manage_stelae` MCP tool is now served directly by the `stelae` bridge. Calls such as `tools/call name="manage_stelae"` stay connected even while the proxy restarts. Under the hood the tool updates templates/overrides and then runs `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`, waiting for the proxy to come back before replying. Override the restart flags via `STELAE_RESTART_ARGS` if you need a different flow.
- CLI examples (identical payload shape to the MCP tool):
  ```bash
  # Inspect discovery output
  python scripts/stelae_integrator_server.py --cli --operation list_discovered_servers

  # Preview a server install without writing files or restarting
  python scripts/stelae_integrator_server.py --cli --operation install_server \
    --params '{"name": "demo_server", "dry_run": true}'
  ```
- Catalog overrides that hydrate descriptors (for example the Qdrant MCP) may require new environment keys. When `manage_stelae` encounters missing keys it appends safe defaults to your local `.env` automatically, keeping `.env.example` generic for fresh clones.
- Supported operations:
  - `discover_servers` – Calls the vendored 1mcp catalogue to find candidates. Accepts `query`, `tags` (list or comma-separated), `preset`, `limit`, `min_score`, `append`, and `dry_run`. The response now echoes the matching descriptors under `details.servers` so you can immediately pick a `name` to install without running `list_discovered_servers`.
  - `list_discovered_servers` – Normalized entries + validation issues, helpful when vetting 1mcp output.
  - `install_server` – Accepts `name` (from discovery) or a full `descriptor` payload, optional `dry_run`, `force`, `target_name`, `options`, and `force_restart`.
  - `remove_server` – Removes template + override entries and restarts the stack (with `dry_run` previews available).
  - `refresh_discovery` – Copies `${ONE_MCP_DIR}/discovered_servers.json` (or a supplied `source_path`) into the tracked cache, returning a diff so you can see what changed.
  - `run_reconciler` – Re-runs `make render-proxy` + the restart script without touching configs; handy after manual template edits.
- For terminal-first workflows set the env overrides inline and call `make discover-servers`, e.g. `DISCOVER_QUERY="vector search" DISCOVER_LIMIT=5 DISCOVER_DRY_RUN=1 make discover-servers`. Supported env knobs mirror the MCP payload (`DISCOVER_QUERY`, `DISCOVER_TAGS`, `DISCOVER_PRESET`, `DISCOVER_LIMIT`, `DISCOVER_MIN_SCORE`, `DISCOVER_APPEND`, `DISCOVER_DRY_RUN`).
- `manage_stelae` now ships in the proxy manifest like any other downstream server; the streamable bridge only injects a local fallback descriptor if the proxy catalog is missing the tool (for example during restart). Codex sessions keep working, but once the proxy is healthy all calls flow through the canonical manifest entry.
- The tool reports file diffs, commands executed, proxy readiness waits, and warnings/errors in a uniform JSON envelope. All validations happen before any file writes so a missing binary or placeholder halts the operation early.
- Manual override-only workflows remain supported via `python scripts/populate_tool_overrides.py --servers <name> --dry-run`, which refreshes schemas without consulting the discovery cache.
- For non-MCP workflows you can inspect the catalogue directly via `scripts/one_mcp_discovery.py "vector search" --limit 10`, which uses the same backend as `discover_servers` and, unless `--dry-run` is set, merges the results into `config/discovered_servers.json`.

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

The helper script `scripts/run_restart_stelae.sh --full` wraps the full cycle (rebuild proxy, render config, restart PM2 fleet, redeploy Cloudflare worker, republish manifest) and is the fastest way to validate override changes end-to-end. When invoked by `manage_stelae` the script is called with `--keep-pm2 --no-bridge --full` so the MCP bridge stays connected; run it without those flags if you truly need a cold restart.

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
