# Stelae MCP Architecture

## Overview

Stelae combines a Go-based MCP aggregation proxy, a fleet of downstream MCP servers, a FastMCP bridge for stdio clients, and a Cloudflare tunnel for public access. Everything originates from the local WSL workspace while remaining consumable by remote ChatGPT Connectors.

### Config overlays

Templates live under `config/` in this repo; all machine-specific state is written to `${STELAE_CONFIG_HOME}` (default `~/.config/stelae`). Each template gains a `*.local.*` companion file the first time you edit it via `manage_stelae`/renderers, and runtime artifacts such as `${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${STELAE_DISCOVERY_PATH}`, `${TOOL_SCHEMA_STATUS_PATH}`, and `${STELAE_CONFIG_HOME}/cloudflared.yml` are emitted there as well. Deleting the corresponding `*.local.*` file is enough to reset a config back to the tracked default. Environment values obey the same layering: `.env.example` stays generic, `.env` is human-edited, and `${STELAE_CONFIG_HOME}/.env.local` (or the last env file provided to the integrator) receives hydrated defaults so git remains clean even when overrides introduce new variables.

Hygiene guardrail: `pytest tests/test_repo_sanitized.py` fails if tracked templates reintroduce absolute `/home/...` paths or if `.env.example` stops pointing runtime outputs at `${STELAE_CONFIG_HOME}`. Run it after touching configs to ensure `make render-proxy` followed by normal stack usage leaves `git status` clean.

`make verify-clean` wraps the same automation path contributors run manually: it snapshots `git status`, executes `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`, and then asserts the working tree matches the pre-run snapshot. Any tracked drift now fails the check immediately.

### Core vs optional bundle

- **Tracked core:** custom tools, the Stelae integrator, the tool aggregator helper, the 1mcp stdio agent, and the public 1mcp catalog bridge (plus the Go proxy and FastMCP bridge). These five servers ship in `config/proxy.template.json` so every clone can immediately discover and manage downstream MCP servers.
- **Starter bundle:** Docy + Docy manager, Basic Memory, Strata, Fetch, Scrapling, Cloudflared/worker helpers, filesystem/ripgrep/terminal controllers, and any other discovery-fed servers defined in `config/bundles/starter_bundle.json`. Install them (along with their overrides/aggregations) via `python scripts/install_stelae_bundle.py` so they only touch `${STELAE_CONFIG_HOME}/config/*.local.json`.
- Optional modules keep their writable state (`config/*.local.json`, `.env.local`, discovery caches) under `${STELAE_CONFIG_HOME}`. Delete a `.local` file or rerun the installer to move between the slim core and the starter bundle without mutating tracked templates.

### Legend

```text
┌──────────────┐  System / long-lived process
╔══════════════╗  External service (Cloudflare, ChatGPT, etc.)
(  Rounded box )  Ephemeral request/response payload or intermediate document
-->             HTTP(S) / SSE request (labelled as needed)
-.->            stdio / local IPC (labelled "stdio")
==>             Internal data merge / transformation
```

## Catalog Aggregation & Overrides

```mermaid
flowchart LR
    subgraph Downstream Servers
        FS["┌──────────────┐<br>Filesystem MCP"]
        RG["┌──────────────┐<br>Ripgrep MCP"]
        DOCS["┌──────────────┐<br>Docy MCP"]
        MEM["┌──────────────┐<br>Basic Memory"]
        STRATA["┌──────────────┐<br>Strata MCP"]
        FETCH["┌──────────────┐<br>Fetch MCP"]
    end

    FS -. stdio .-> PROXY
    RG -. stdio .-> PROXY
    DOCS -. stdio .-> PROXY
    MEM -. stdio .-> PROXY
    STRATA -. stdio .-> PROXY
    FETCH -. stdio .-> PROXY

    TOOLJSON["[ tools/list JSON ]"]
    INITJSON["[ initialize result ]"]
    MANIFEST["[ manifest document ]"]

    TO_CFG["┌──────────────┐<br>config/tool_overrides.json"]
    MAN_CFG["┌──────────────┐<br>manifest.toolOverrides"]
    toSet(((Override<br>resolver)))

    PROXY["┌──────────────┐<br>mcp-proxy (Go facade)"]
    TO_CFG ==>|JSON load| toSet
    MAN_CFG ==>|template overrides| toSet

    PROXY ==> |merge descriptors| toSet
    toSet ==>|enabled? + annotations + schemas| TOOLJSON
    toSet ==>|enabled? + annotations + schemas| INITJSON
    toSet ==>|enabled? + annotations + schemas| MANIFEST

    PROXY ==> |fallback| TOOLJSON
    PROXY ==> |fallback| INITJSON
    PROXY ==> |fallback| MANIFEST

    TOOLJSON -->|exposed via JSON-RPC `tools/list`| CLIENTS
    INITJSON -->|JSON-RPC `initialize`| CLIENTS
    MANIFEST -->|/.well-known/mcp/manifest.json| CLIENTS

    subgraph Consumers
        CLIENTS["╔══════════════╗<br>ChatGPT +<br>Streamable clients"]
    end
```

* Downstream MCP servers register their tool descriptors during startup (`collectTools`).
* Overrides are merged in the following order:
  1. `manifest.toolOverrides` from `config/proxy.json`.
  2. The overrides template (`config/tool_overrides.json`, validated via `config/tool_overrides.schema.json`) + your `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json`. Each tool override lives under its server while the `master.tools["*"]` wildcard provides shared defaults, and the merged runtime file at `${TOOL_OVERRIDES_PATH}` is what the proxy consumes.
  3. Master (`*`) overrides apply last.
* Overrides can rewrite names, descriptions, annotations, and full `inputSchema`/`outputSchema` blocks. We use this to advertise the adapted contract the proxy enforces at call time.
* Scrapling’s `s_fetch_page` and `s_fetch_pattern` entries in the overrides template feed the runtime file `${TOOL_OVERRIDES_PATH}`. The call-path adapter in the Go proxy writes back to the runtime file whenever it has to downgrade/upgrade a schema; rerun `make render-proxy` + the restart script after editing those overrides so manifests and streamable clients see the update immediately.
* The proxy filters out any tool/server marked `enabled: false` before producing `initialize`, `tools/list`, and manifest payloads.
* Every `tools/list` descriptor carries `"x-stelae": {"servers": [...], "primaryServer": "..."}` metadata. The restart script + populate helper rely on this to map schemas back to the correct server even after the proxy deduplicates tool names.
* Declarative aggregations are described in `config/tool_aggregations.json`, but the tracked template now only contains the schema defaults and the `facade.search` hide rule. Run `python scripts/install_stelae_bundle.py` to seed `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json` with the full definitions from `config/bundles/starter_bundle.json`. `scripts/process_tool_aggregations.py` validates the merged file, writes the resulting descriptors to `${TOOL_OVERRIDES_PATH}`, and sets any `hideTools` entries to `enabled: false`. `scripts/tool_aggregator_server.py` loads the same config at runtime so wrappers such as `manage_docy_sources` show up once in manifests even though they fan out to underlying servers.

## Operations & Troubleshooting

### Troubleshooting quick reference

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `mcp-proxy` not listening on `:9090` | Go build failed or pm2 stopped | `./scripts/run_restart_stelae.sh` or `source ~/.nvm/nvm.sh && pm2 restart mcp-proxy` |
| Override hints missing from manifest | runtime overrides not loaded or stale | confirm `${TOOL_OVERRIDES_PATH}` is valid JSON, rerun `make render-proxy`, then `scripts/run_restart_stelae.sh --full` |
| `tools/call search` returns `{ "results": [] }` | running an old version; static hits missing | rebuild Go proxy (`facade_search.go`) and restart |
| Codex CLI reports “MCP client … request timed out” | STDIO bridge launched without proper env | ensure the Codex config exports `PYTHONPATH=/home/gabri/dev/stelae` and `STELAE_STREAMABLE_TRANSPORT=stdio`; run `make check-connector` locally |
| Cloudflare 530 splash | tunnel momentarily unhealthy | rerun `scripts/run_restart_stelae.sh --full` (validates tunnel + pm2), or `source ~/.nvm/nvm.sh && pm2 restart cloudflared` |
| `make check-connector` flags unexpected catalog | new upstream tools exposed or overrides missing | inspect `logs/mcp-proxy.err.log`, confirm `${TOOL_OVERRIDES_PATH}` is current, rerun restart |
| Startup logs mention "master override" warnings | master-level description/title overrides present | keep only the wildcard `"*"` entry under `master.tools`; move other overrides under their server |
| `tools/call fetch` returns network errors | upstream site blocked / fetch server delay | retry or inspect `logs/fetch.err.log` |
| SSE drops quickly | Cloudflare idle timeout | ensure Go proxy heartbeat loop is running (keepalives every 15s) |

### Reference commands

```bash
# PM2 management
source ~/.nvm/nvm.sh
pm2 status
pm2 logs mcp-proxy --lines 150
pm2 restart cloudflared

# Re-run public probe & archive log
CONNECTOR_BASE=https://mcp.infotopology.xyz/mcp make check-connector

# Manual STDIO smoke test (inside WSL)
python - <<'PY'
import os, anyio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

params = StdioServerParameters(
    command='/home/gabri/.venvs/stelae-bridge/bin/python',
    args=['-m', 'scripts.stelae_streamable_mcp'],
    env={
        'PYTHONPATH': '/home/gabri/dev/stelae',
        'STELAE_PROXY_BASE': 'http://127.0.0.1:9090',
        'STELAE_STREAMABLE_TRANSPORT': 'stdio',
        'PATH': os.environ['PATH'],
    },
    cwd='/home/gabri/dev/stelae',
)

async def main():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(init.serverInfo)
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

anyio.run(main)
PY
```

### Clone smoke harness

- `scripts/run_e2e_clone_smoke_test.py` provisions a throwaway workspace, clones Stelae + `mcp-proxy`, writes an isolated `.env`/`${STELAE_CONFIG_HOME}`, renders the proxy, restarts the stack with a sandboxed `PM2_HOME`, and installs/removes `docy_manager` via the `manage_stelae` CLI to confirm tracked templates stay untouched.
- The harness emits `manual_playbook.md` and `manual_result.json` in the workspace. Follow the playbook to launch the Codex MCP wrapper (provide `--wrapper-release` so the release is mirrored into `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<version>`), run the mission in `dev/tasks/missions/e2e_clone_smoke.json`, and update `manual_result.json` with `status: "passed"` plus the wrapper call IDs.
- After the tester returns to the harness prompt and confirms completion, the script validates the manual result, kills the sandbox PM2 daemon, and deletes the workspace unless `--keep-workspace` is set. Full prerequisites and CLI options live in `docs/e2e_clone_smoke_test.md`.

### Tool aggregation helper

**Why:** Operators wanted a way to expose curated, high-level tools without duplicating logic across MCP servers or manually editing the overrides template. The aggregation helper keeps the catalog clean by letting us describe composites in JSON, hide the noisy downstream entries, and reuse the existing proxy infrastructure for dispatch.

**How it works:**

1. `config/tool_aggregations.json` declares each aggregate tool (manifest metadata, per-operation mappings, validation hints, and a `hideTools` list). The tracked template is a stub; the starter bundle populates `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json` with the real entries, and the merged payload still obeys `config/tool_aggregations.schema.json` so CI / restart scripts can lint config changes early.
2. `scripts/process_tool_aggregations.py` runs during `make render-proxy` and the restart workflow. It loads the merged config (repo template + `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json`), writes/upgrades the matching entries in `${TOOL_OVERRIDES_PATH}`, and flips every `hideTools` entry (`server/tool`) to `enabled: false` so manifests/initialize/tools.list only expose the aggregate.
3. `scripts/tool_aggregator_server.py` is a FastMCP stdio server launched by the proxy. On startup it registers one MCP tool per aggregation; at call time it validates the input per the declarative mapping rules, translates arguments into the downstream schema, and uses the proxy JSON-RPC endpoint to call the real tool. Response mappings (optional) can reshape the downstream payload before returning to the client.
4. Because both the overrides and the stdio helper derive from the same config, adding a new aggregate requires zero Python changes—edit the JSON, run `make render-proxy`, and the proxy automatically restarts the helper with the new catalog.

Current suites declared in `config/tool_aggregations.json`:

- `workspace_fs_read` – consolidates all read-only filesystem helpers (`list_*`, `read_*`, `find_*`, `search_*`, `get_file_info`, `calculate_directory_size`).
- `workspace_fs_write` – wraps the mutating filesystem helpers (`create_directory`, `edit_file`, `write_file`, `move_file`, `delete/insert/zip/unzip`).
- `workspace_shell_control` – exposes guarded terminal-controller actions (`execute_command`, `change_directory`, `get_current_directory`, `get_command_history`).
- `memory_suite` – surfaces every Basic Memory operation (context build, CRUD, project switching, searches) behind a single manifest entry.
- `doc_fetch_suite` – unifies Docy fetch helpers (`fetch_document_links`, `fetch_documentation_page`, `list_documentation_sources_tool`).
- `scrapling_fetch_suite` – selects the Scrapling fetch mode (`s_fetch_page`, `s_fetch_pattern`).
- `strata_ops_suite` – aggregates Strata’s discovery/execution/auth workflows (`discover_server_actions`, `execute_action`, `get_action_details`, `handle_auth_failure`, `search_documentation`).
- `manage_docy_sources` – Docy catalog administration (list/add/remove/sync/import).

If `tools/list` ever shrinks to the fallback `fetch`/`search` entries, the aggregator likely failed to register; rerun `make restart-proxy` (or `scripts/run_restart_stelae.sh --full`) to relaunch the stdio server and restore the curated catalog.
* The proxy records per-tool adapter state in `${TOOL_SCHEMA_STATUS_PATH}` (path set through `manifest.toolSchemaStatusPath`) and patches `${TOOL_OVERRIDES_PATH}` whenever call-path adaptation selects a different schema (e.g., persisting generic for text-only servers). After rerunning `make render-proxy` + restarting PM2, external clients see the updated schemas. `scripts/populate_tool_overrides.py --proxy-url <endpoint> --quiet` now runs during `scripts/restart_stelae.sh` so every restart reuses the freshly collected `tools/list` payload to ensure all downstream schemas are persisted; the script still supports per-server scans for development via `--servers`, and operators can opt out entirely for a given restart with `--skip-populate-overrides`. When invoking manually, export `PYTHONPATH=$STELAE_DIR` so the helper can import `stelae_lib`.
* Facade fallback descriptors (`search`, `fetch`) remain available even if no downstream server supplies them, and they can also be overridden via the master block.

## Request / Response Paths

```mermaid
sequenceDiagram
    participant ChatGPT
    participant Cloudflare as ╔Cloudflare Tunnel╗
    participant Proxy as ┌mcp-proxy┐
    participant Servers as ┌Downstream MCPs┐
    participant Bridge as ┌stelae_streamable_mcp┐

    ChatGPT->>Cloudflare: HTTPS GET /.well-known/mcp/manifest.json
    Cloudflare->>Proxy: HTTPS (internal) GET
    Proxy->>Proxy: buildManifestDocumentWithOverrides()
    Proxy-->>Cloudflare: Manifest JSON
    Cloudflare-->>ChatGPT: Manifest JSON

    ChatGPT->>Cloudflare: HTTPS POST /mcp (initialize)
    Cloudflare->>Proxy: Forward JSON-RPC request
    Proxy->>Servers: stdio initialize/listTools/listPrompts/etc.
    Servers-->>Proxy: Tool & prompt catalog
    Proxy->>Proxy: collectTools + overrides
    Proxy-->>Cloudflare: JSON-RPC result
    Cloudflare-->>ChatGPT: JSON-RPC result

    Note over Bridge,Proxy: Local IDE clients speak stdio via FastMCP bridge.
    Bridge->>Proxy: stdio initialize/tools.call
    Proxy->>Servers: stdio callTool
    Servers-->>Proxy: downstream result
    Proxy-->>Bridge: aggregated response
    Bridge-->>IDE: streamable/stdio payload
```

* Remote clients traverse the Cloudflare tunnel; local clients use the FastMCP bridge (`scripts/stelae_streamable_mcp.py`).
* All paths share the same override-aware catalog inside the Go facade, guaranteeing consistent visibility between local and remote consumers.
* `manage_stelae` originates from the Go proxy manifest; the FastMCP bridge only injects a fallback descriptor (and short-circuits calls) if the proxy catalog is temporarily missing the tool. Once the proxy restarts cleanly, everything flows through the canonical manifest entry.

## Component Topology

```mermaid
flowchart TD
    subgraph PM2
        A["┌──────────────┐<br>mcp-proxy"]
        B["┌──────────────┐<br>stelae_streamable_mcp"]
        C["┌──────────────┐<br>cloudflared"]
        D["┌──────────────┐<br>watchdog"]
    end

    subgraph MCP Servers
        FS[Filesystem]
        RG[Ripgrep]
        SH[Shell]
        DOCS[Docy]
        MEM[Memory]
        FETCH[Fetch]
        STRATA[Strata]
        INT[Integrator]
    end

    A ==▷|stdio| FS
    A ==▷|stdio| RG
    A ==▷|stdio| SH
    A ==▷|stdio| DOCS
    A ==▷|stdio| MEM
    A ==▷|stdio| FETCH
    A ==▷|stdio| STRATA
    A ==▷|stdio| INT

    B ==▷|stdio| A
    A --▶|HTTP/SSE :9090| C
    C --▶|HTTPS| Public(("╔ChatGPT / Clients╗"))

    D --▶|diagnostic probes| C
    D --▶|pm2 restart| C

    Config["┌──────────────┐<br>config/proxy.json"] --> A
    Overrides["┌──────────────┐<br>${TOOL_OVERRIDES_PATH}"] --> A
```

## Discovery & Auto-Loading Pipeline

0. Run `python scripts/bootstrap_one_mcp.py` after cloning. The helper clones or updates the forked `~/apps/vendor/1mcpserver`, runs `uv sync`, ensures `config/discovered_servers.json` exists, and writes a ready-to-use `~/.config/1mcp/mcp.json`. This keeps upstream repos read-only and makes discovery reproducible for every contributor.
1. The 1mcp agent watches the workspace and writes normalized descriptors to `config/discovered_servers.json` (one array of `{name, transport, command|url, args, env, tools, options}` objects). The file is tracked in git so proposed additions can be reviewed. The `discover_servers` operation in `manage_stelae` can also populate this cache directly, taking `query` + optional `tags`, `preset`, `limit`, and `min_score` filters. The results array echoes the fully normalised descriptors so operators can install them without a follow-up `list_discovered_servers` call. CLI folks can run `make discover-servers` (wrapper around `scripts/discover_servers_cli.py`) to drive the same operation via env vars when MCP isn’t involved.
2. During discovery the integrator applies catalog overrides for known slugs (for example Qdrant) so metadata-only entries gain runnable transport/command/env fields immediately. When an override introduces new env keys, the tool appends safe defaults to the writable env overlay (defaults to `${STELAE_CONFIG_HOME}/.env.local`, or the final `env_files` entry provided) so tracked `.env`/`.env.example` stay generic yet installs succeed without manual edits.
3. `scripts/stelae_integrator_server.py` exposes the `manage_stelae` tool (and CLI) which loads the discovery cache, validates descriptors, and transforms them through three focussed helpers. The MCP bridge advertises the tool locally so Codex/clients call `stelae.manage_stelae` directly instead of shelling out:
   - `DiscoveryStore` normalises transports (`stdio`, `http`, `streamable-http`), cleans args/env, and flags incomplete entries.
   - `ProxyTemplate` ensures `config/proxy.template.json` gains sorted server stanzas, raising unless `force` is set when a duplicate exists.
   - `ToolOverridesStore` pre-populates `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json` (and therefore `${TOOL_OVERRIDES_PATH}`) with descriptions and tool metadata so manifests stay descriptive from the first render.
4. After writing files (or emitting diffs during dry-runs) the integrator re-runs `make render-proxy` and `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared`, guaranteeing local parity (proxy + stdio bridge) even when operators lack Cloudflare credentials. Set `STELAE_RESTART_ARGS` to override those flags (for example `--full` to redeploy the tunnel + manifest). The tool waits for the proxy’s JSON-RPC health probes to succeed before returning.
5. Operations available through `manage_stelae`/CLI: `discover_servers`, `list_discovered_servers`, `install_server`, `remove_server`, `refresh_discovery`, and `run_reconciler`. Every response shares a single envelope containing `status`, `details`, `files_updated`, `commands_run`, `warnings`, and `errors` for easier automation.
6. Guardrails: commands referenced in descriptors must resolve on disk or via `.env` placeholders (`{{KEY}}`). The tool fails fast if binaries/vars are missing, before any template changes occur, and refuses to overwrite `.env.example` to keep the repo clone-friendly.

## Operational Notes

1. `make render-proxy` regenerates `config/proxy.json`, preserving the override file path.
2. `bash scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` rebuilds the proxy, restarts PM2 processes, and validates the local JSON-RPC flow—this is the default path invoked by `manage_stelae`, keeping contributor laptops functional without requiring a tunnel. Append `--full` when you explicitly need to redeploy Cloudflare (manifest push + tunnel restart). The helper prints one-line `pm2 ensure <app>: status=<prev> -> <action>` entries so operators can see whether it started a missing process, deleted+started an unhealthy one, or simply refreshed an online entry.
3. `scripts/watch_public_mcp.py` shares the same `pm2 ensure` logic; when the public JSON-RPC probes fail it can now recreate `cloudflared` (delete+start) instead of looping on `pm2 restart`.
4. To temporarily hide a tool or server from clients, set `"enabled": false` via the overrides overlay (`${STELAE_CONFIG_HOME}/config/tool_overrides.local.json`) or template, rerun `make render-proxy`, then execute the restart script.

This document should serve as the reference for future diagnostics or enhancements to the catalog pipeline and transport topology.
