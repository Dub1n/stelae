# Development Guide

Internal reference for maintaining and extending the Stelae MCP stack. Use this document once the public-facing README gets you oriented; everything below assumes you are comfortable editing templates, restarting services, and running tests locally.

## Table of Contents

- [Overview](#overview)
- [Stack Snapshot](#stack-snapshot)
- [Environment Setup](#environment-setup)
- [Workflow Guardrails](#workflow-guardrails)
- [Operating the Stack](#operating-the-stack)
- [Catalog, Aggregations, and Custom Tools](#catalog-aggregations-and-custom-tools)
- [Discovery and Server Management](#discovery-and-server-management)
- [Remote Access](#remote-access)
- [Validation and Diagnostics](#validation-and-diagnostics)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)
- [Related Files](#related-files)

## Overview

Stelae runs a Go-based MCP aggregation proxy, a fleet of downstream MCP servers, and an optional Cloudflare tunnel so remote agents can use the same catalog as local stdio clients. The `Dub1n/mcp-proxy` fork ships a `/mcp` HTTP facade that powers the restart helper, FastMCP bridge, and clone-smoke harness.

Tracked templates live under `config/`; human-edited overlays and bundle data live under `${STELAE_CONFIG_HOME}` (default `~/.config/stelae`); runtime artifacts (proxy config, intended/live catalog snapshots, schema status) live under `${STELAE_STATE_HOME}` (default `${STELAE_CONFIG_HOME}/.state`). Guard every mutable path with `require_home_path` so files stay under those roots.

## Stack Snapshot

| Component | Profile | Transport | Launch Command | Purpose |
|-----------|---------|-----------|----------------|---------|
| mcp-proxy | default | HTTP/SSE (:${PROXY_PORT:-9090}) | `${PROXY_BIN}` | Aggregates tools/prompts/resources into one endpoint. |
| Filesystem MCP | local | stdio | `${FILESYSTEM_BIN} --root ${STELAE_DIR}` | Scoped repo read/write. |
| ripgrep MCP | local | stdio | `${RG_BIN} --stdio --root ${SEARCH_ROOT}` | Code search backing the `grep` tool. |
| Commands MCP | local | stdio | `${NPX_BIN}` | Runs `g0t4/mcp-server-commands` so helpers execute inside the repo. |
| Tool aggregator MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/tool_aggregator_server.py` | Publishes declarative composite tools from config-home catalog fragments (`${STELAE_CONFIG_HOME}/catalog/*.json`) plus bundle fragments (`${STELAE_CONFIG_HOME}/bundles/*/catalog.json`). |
| Stelae integrator MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/stelae_integrator_server.py` | Consumes 1mcp discovery output, updates templates/overrides, and restarts the stack via `manage_stelae`. |
| Basic Memory MCP | local | stdio | `${MEMORY_BIN}` | Persistent project memory (starter bundle). |
| Strata MCP | local | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing (starter bundle). |
| Fetch MCP | local | HTTP | `${LOCAL_BIN}/mcp-server-fetch` | Canonical `fetch`. |
| Scrapling MCP | local | stdio | `uvx scrapling-fetch-mcp --stdio` | Scrapling fetcher (basic/stealth/max-stealth) adapted by the proxy. |
| FastMCP bridge | default | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Exposes the full catalog to desktop agents; falls back to local search/fetch if the proxy is unavailable. |
| 1mcp agent | default | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovers nearby MCP servers and writes `${STELAE_DISCOVERY_PATH}` (defaults to `${STELAE_STATE_HOME}/discovered_servers.json`). |
| Custom tools MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/custom_tools_server.py` | Wraps scripts listed in `${STELAE_CONFIG_HOME}/custom_tools.json`. |

Core templates ship the essentials (custom tools, Stelae integrator, tool aggregator helper, 1mcp stdio agent, public 1mcp bridge, Go proxy, FastMCP bridge). Optional suites (filesystem helpers, memory, fetch, etc.) are installed via the folder-based starter bundle.

## Environment Setup

### Prerequisites

- Python 3.11+ with virtualenv support (`scripts/setup_env.py` handles creation).
- Go toolchain for rebuilding `mcp-proxy` under `~/apps/mcp-proxy`.
- Node.js via NVM for PM2 management.
- Cloudflare CLI + named tunnel credentials when exposing the stack publicly.

### Initial configuration

1. Run `python scripts/setup_env.py` to materialize `.env` entries and automatically seed/repair catalog, overrides, custom tool, and runtime JSON stubs inside `${STELAE_CONFIG_HOME}` / `${STELAE_STATE_HOME}`. The helper now relocates stray files by name, so if you ever delete `tool_overrides.json` (or move `catalog/core.json`) it silently recreates or recovers them.
2. Edit `${STELAE_ENV_FILE}` (default `${STELAE_CONFIG_HOME}/.env`) and `${STELAE_CONFIG_HOME}/.env.local` with machine-specific paths/binaries. `.env.example` stays generic.
3. Rebuild the Go proxy if sources change: `pushd ~/apps/mcp-proxy && go build -o build/mcp-proxy && popd`.
4. Install or refresh optional suites via `python scripts/install_stelae_bundle.py [--server name]`.

### Config layering

- Templates stay in-repo (`config/*.template.json`).
- `${STELAE_CONFIG_HOME}` stores editable overlays, bundles, `custom_tools.json`, and discovery cache.
- `${STELAE_STATE_HOME}` stores runtime artifacts: `${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${INTENDED_CATALOG_PATH}`, `${STELAE_STATE_HOME}/live_catalog.json`, `${TOOL_SCHEMA_STATUS_PATH}`, drift logs, metrics, etc.
- `require_home_path` enforces that anything mutable remains inside those homes.

## Workflow Guardrails

Follow this loop whenever templates or catalog fragments change:

1. `python scripts/process_tool_aggregations.py --scope local` – validates `${STELAE_CONFIG_HOME}/catalog/*.json` + bundle fragments, writes `${TOOL_OVERRIDES_PATH}` and `${INTENDED_CATALOG_PATH}` into `${STELAE_STATE_HOME}`.
2. `make render-proxy` – refreshes `${PROXY_CONFIG}` and merged overrides, pulling from `${STELAE_STATE_HOME}/live_descriptors.json` (pass `--allow-stale-descriptors` only when investigating drift).
3. `pytest tests/test_repo_sanitized.py` – ensures templates remain placeholder-only.
4. `make verify-clean` (or `./scripts/verify_clean_repo.sh --skip-restart`) – wraps render + restart automation and fails when tracked drift appears.

`STELAE_USE_INTENDED_CATALOG=1` ships in `.env.example`, so restarts prefer `${INTENDED_CATALOG_PATH}` and treat `${TOOL_OVERRIDES_PATH}` as a fallback. Toggle per run via `scripts/run_restart_stelae.sh --intended-catalog|--legacy-catalog` or export the env var when debugging.

After restarts, `scripts/restart_stelae.sh` captures `${STELAE_STATE_HOME}/live_catalog.json`, diffs intended vs live via `scripts/diff_catalog_snapshots.py --fail-on-drift`, records metrics, and prunes catalog history.

## Operating the Stack

### PM2 lifecycle

```bash
source ~/.nvm/nvm.sh
make up                     # start processes and save the PM2 list
make down                   # stop everything
source ~/.nvm/nvm.sh && pm2 status
source ~/.nvm/nvm.sh && pm2 logs --lines 50
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```

Logs land under `logs/` (see `ecosystem.config.js`). Always source NVM before touching PM2.

### Restart helper

`scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` rebuilds the proxy, re-renders configs, restarts the PM2 fleet, and captures catalog drift. Pass `--full` when you also need to push manifests to Cloudflare KV and restart the tunnel/worker. The helper prints per-process summaries (e.g., `pm2 ensure cloudflared: status=errored -> delete+start`). Override behavior via `STELAE_RESTART_ARGS`.

### FastMCP bridge and local consumers

`scripts/stelae_streamable_mcp.py` exposes the proxy catalog to desktop clients. Configure Codex CLI/TUI by adding this entry to `~/.codex/config.toml`:

```toml
[mcp_servers.stelae]
command = "/home/gabri/.venvs/stelae-bridge/bin/python"
args = ["-m", "scripts.stelae_streamable_mcp"]
env = {
  "PYTHONPATH" = "/home/gabri/dev/stelae",
  "STELAE_STREAMABLE_TRANSPORT" = "stdio",
  "STELAE_PROXY_BASE" = "http://127.0.0.1:9090"
}
startup_timeout_sec = 30
tool_timeout_sec = 180
```

Keep `STELAE_PROXY_BASE` pointed at the bare origin; the bridge appends `/mcp` internally and falls back to minimal `search`/`fetch` tooling if the handshake fails.

## Catalog, Aggregations, and Custom Tools

### Declarative tool aggregations

- Catalog fragments live under `${STELAE_CONFIG_HOME}/catalog/*.json` plus `${STELAE_CONFIG_HOME}/bundles/*/catalog.json`. Validate them with `python scripts/process_tool_aggregations.py --check-only`.
- Aggregated tools return downstream `content` blocks and preserve `structuredContent`. The runner bypasses FastMCP’s coercion via a custom `FuncMetadata` shim and decodes JSON-looking strings to keep structured results typed.
- Bundle descriptors may declare `downstreamServer`; the aggregator forwards that as `serverName` so composites such as `workspace_fs_read` continue to call the intended backend even when overrides hide or rename tools.
- Aggregated tool `outputSchema.type` is normalized to `"object"` for Codex compatibility. If Stelae tools disappear from `list_tools`, rerun `python scripts/process_tool_aggregations.py --scope local` and `make render-proxy`.

To add an aggregate:

1. Copy an existing block from `bundles/starter/catalog.json` (or your `${STELAE_CONFIG_HOME}/catalog/*.json`).
2. Adjust metadata, `operations`, argument mappings, response mappings, and `hideTools`.
3. Run `python scripts/process_tool_aggregations.py --check-only` to lint.
4. Render + restart so `${TOOL_OVERRIDES_PATH}` and `${INTENDED_CATALOG_PATH}` refresh.

### Custom script tools

`scripts/custom_tools_server.py` loads `${STELAE_CONFIG_HOME}/custom_tools.json` (override via `STELAE_CUSTOM_TOOLS_CONFIG`). Each entry may include `name`, `description`, `command`, optional `args`, `cwd`, `env`, `timeout`, and `inputMode` (`json` or `none`). Example:

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

After editing `custom_tools.json`, rerun `make render-proxy` and restart PM2 so the manifest picks up the changes. Legacy `search`/`fetch` fallbacks stay disabled through config-home overrides.

## Discovery and Server Management

### Bootstrapping 1mcp

`python scripts/bootstrap_one_mcp.py` clones or updates `stelae-1mcpserver` under `${ONE_MCP_DIR:-~/apps/vendor/1mcpserver}`, runs `uv sync`, ensures `${STELAE_DISCOVERY_PATH}` exists, and writes `~/.config/1mcp/mcp.json` (override via `--config`). The generated snippet looks like:

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
  "discovery": {"cachePath": "${STELAE_DISCOVERY_PATH}"}
}
```

Re-run bootstrap whenever the repo moves or you need to refresh the CLI config. Use `--skip-update`/`--skip-sync` to only rewrite config files.

### `manage_stelae` operations

- 1mcp writes discovery payloads to `${STELAE_DISCOVERY_PATH}`. Keep tracked templates generic; all discoveries stay in config-home.
- `manage_stelae` runs inside the FastMCP bridge and stays available while the proxy restarts. It updates templates/overrides, calls `make render-proxy`, and runs `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` (unless overridden).
- Override restart behavior with `STELAE_RESTART_ARGS` when you need Cloudflare pushes or other flags.

Operations:

- `discover_servers` – query the vendored 1mcp catalog (`query`, `tags`, `preset`, `limit`, `min_score`, `append`, `dry_run`). Responses echo matching descriptors.
- `list_discovered_servers` – normalized entries plus validation issues.
- `install_server` – accepts `name` or explicit descriptor, optional `dry_run`, `force`, `target_name`, `options`, `force_restart`.
- `remove_server` – deletes template + override entries (dry-run supported).
- `refresh_discovery` – copies `${ONE_MCP_DIR}/discovered_servers.json` (or `--source-path`) into `${STELAE_DISCOVERY_PATH}` and returns a diff.
- `run_reconciler` – re-runs render + restart without editing configs.

For terminal workflows you can call the integrator directly, e.g. `python scripts/stelae_integrator_server.py --cli --operation install_server --params '{"name":"demo_server","dry_run":true}'`, or rely on make wrappers such as `DISCOVER_QUERY="vector search" DISCOVER_LIMIT=5 DISCOVER_DRY_RUN=1 make discover-servers`.

## Remote Access

### Cloudflare named tunnel

`~/.cloudflared/config.yml` should resemble:

```yaml
tunnel: stelae
credentials-file: ~/.cloudflared/7a74f696-46b7-4573-b575-1ac25d038899.json

ingress:
  - hostname: mcp.infotopology.xyz
    service: http://localhost:${PROXY_PORT:-9090}
  - service: http_status:404
```

Operational steps:

1. `cloudflared tunnel route dns stelae mcp.infotopology.xyz`
2. `source ~/.nvm/nvm.sh && pm2 start "cloudflared tunnel run stelae" --name cloudflared && pm2 save`
3. Whenever `.env` or proxy config changes: `make render-proxy`, restart `mcp-proxy` and `cloudflared` via PM2.
4. Validate:

```bash
curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
curl -skI https://mcp.infotopology.xyz/stream
```

### Local vs remote consumers

- Remote agents (ChatGPT, etc.) use the Cloudflare manifest.
- Local MCP clients hit `http://localhost:${PROXY_PORT:-9090}` for the same catalog.
- The FastMCP bridge automatically loads `.env` + `${STELAE_CONFIG_HOME}/.env.local` so MCP helpers see the same env values the proxy uses. If the proxy handshake fails the bridge drops to fallback `search`/`fetch`; restart `stelae-bridge` via PM2 to recover.

## Validation and Diagnostics

### Validation checklist

1. `curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{tools: (.tools | map(.name))}'` shows filesystem, ripgrep, shell, docs, memory, strata, fetch, etc.
2. Exercise `fetch` and `rg/search` from ChatGPT to confirm JSON payloads.
3. `pm2 status` reports `online` for proxy, FastMCP bridge, MCP servers, and `cloudflared`.
4. Optional drift gate: `make check-catalog-drift` (or the diff printed by `scripts/restart_stelae.sh`) fails when intended vs live catalogs diverge unless `STELAE_ALLOW_LIVE_DRIFT=1`. `make catalog-metrics` emits JSON metrics into `${STELAE_STATE_HOME}`; `make prune-catalog-history` trims snapshots.

### Connector readiness

- Ensure the Cloudflare tunnel is up (`pm2 restart cloudflared` as needed) and `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` returns 200.
- Validate manifest sanity locally via the same curl + jq snippet.
- Probe SSE endpoints (excerpt below) whenever debugging streamable transport:

```python
# Minimal SSE smoke test (run inside the FastMCP bridge virtualenv)
import anyio, json, httpx
from anyio import create_memory_object_stream
from httpx_sse import EventSource
from urllib.parse import urlparse
from mcp.client.session import ClientSession
from mcp.client.sse import SessionMessage
from mcp import types

async def smoke_rg():
    url = "http://localhost:${PROXY_PORT:-9090}/rg/sse"
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
                            msg = types.JSONRPCMessage.model_validate_json(sse.data)
                            await read_writer.send(SessionMessage(msg))
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

## Maintenance

| Cadence | Action |
|---------|--------|
| Monthly | `git pull`, rebuild `mcp-proxy`, `pipx upgrade --include-apps`, `npm update -g`, rerun `make render-proxy`, restart services. |
| Quarterly | Audit filesystem roots, shell allowlists, Cloudflare credentials, `.env` paths. |
| As needed | Update `.env` when binaries move, rerun `make render-proxy`, restart PM2 with `--update-env`. |

Keep a backup of `${STELAE_STATE_HOME}/proxy.json` (or rely on git history) before major changes.

## Troubleshooting

- `pm2 status` shows `Permission denied` – source NVM (`source ~/.nvm/nvm.sh`).
- `search` missing – verify the FastMCP bridge virtualenv has dependencies and restart `stelae-bridge` via PM2.
- `fetch` missing – confirm `${LOCAL_BIN}/mcp-server-fetch` exists and is executable.
- `jq: parse error` – wrap queries in single quotes, e.g., `jq '{servers, tools: (.tools | length)}'`.
- Cloudflare 404 on `/stream` – proxy offline or tunnel disconnected; inspect `pm2 logs mcp-proxy` and `pm2 logs cloudflared`.

## Related Files

- `config/proxy.template.json` – rendered into `${STELAE_STATE_HOME}/proxy.json`.
- `scripts/render_proxy_config.py` – templating helper.
- `scripts/stelae_streamable_mcp.py` – FastMCP bridge for stdio clients.
- `scripts/tool_aggregator_server.py` – declarative tool aggregator runtime.
- `scripts/stelae_integrator_server.py` – CLI + MCP tool for discovery/installs.
- `scripts/process_tool_aggregations.py` – catalog merger/validator.
- `docs/e2e_clone_smoke_test.md` – clone-smoke harness details.
- `docs/openai-mcp.md` – SSE harness examples and connector probes.
