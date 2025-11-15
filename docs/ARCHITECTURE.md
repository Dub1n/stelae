# Stelae MCP Architecture

## Overview

Stelae combines a Go-based MCP aggregation proxy, a fleet of downstream MCP servers, a FastMCP bridge for stdio clients, and a Cloudflare tunnel for public access. Everything originates from the local WSL workspace while remaining consumable by remote ChatGPT Connectors. The Go proxy currently comes from the [Dub1n/mcp-proxy](https://github.com/Dub1n/mcp-proxy) fork so we can expose a unified `/mcp` facade (HEAD/GET/POST) for readiness probes and streamable clients while upstreaming the feature.

### Config overlays

Templates live under `config/` in this repo; all machine-specific state is written to `${STELAE_CONFIG_HOME}` (default `~/.config/stelae`). Each template gains a `*.local.*` companion file the first time you edit it via `manage_stelae`/renderers. Runtime artifacts such as `${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, and `${TOOL_SCHEMA_STATUS_PATH}` are emitted into `${STELAE_STATE_HOME}` (defaults to `${STELAE_CONFIG_HOME}/.state`), while overlays (`*.local.json`, discovery caches, `.env.local`) stay alongside the config home. Route any future generated files into `.state` to keep the overlay directory human-editable. Deleting the corresponding `.local` file is enough to reset a config back to the tracked default. Environment values obey the same layering: `.env.example` stays generic, `${STELAE_ENV_FILE}` (default `${STELAE_CONFIG_HOME}/.env`) is human-edited, and `${STELAE_CONFIG_HOME}/.env.local` (or the last env file provided to the integrator) receives hydrated defaults so git remains clean even when overrides introduce new variables. Run `python scripts/setup_env.py` after cloning to seed `${STELAE_ENV_FILE}` and keep `repo/.env` pointing at the config-home copy.

Hygiene guardrail: `pytest tests/test_repo_sanitized.py` fails if tracked templates reintroduce absolute `/home/...` paths or if `.env.example` stops pointing runtime outputs at `${STELAE_CONFIG_HOME}`. Run it after touching configs to ensure `make render-proxy` followed by normal stack usage leaves `git status` clean.

`make verify-clean` wraps the same automation path contributors run manually: it snapshots `git status`, executes `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`, and then asserts the working tree matches the pre-run snapshot. Any tracked drift now fails the check immediately.

**Overlay workflow:** after editing tracked templates run `python scripts/process_tool_aggregations.py --scope default`, then `python scripts/process_tool_aggregations.py --scope local`, followed by `make render-proxy` and `pytest tests/test_repo_sanitized.py`. This guarantees `${STELAE_CONFIG_HOME}` (human-edited overlays) and `${STELAE_STATE_HOME}` (generated artifacts) stay in sync. Run `make verify-clean` before publishing manifest changes so restart automation proves `git status` remains empty. The consolidated workbook in `dev/tasks/stelae-smoke-readiness.md` references this loop whenever catalog or harness work begins.

#### Overlay → runtime render flow

```mermaid
flowchart LR
    Templates["Tracked templates<br/>(config/*.template.*)"]
    LocalOverlays["${STELAE_CONFIG_HOME}/*.local.json<br/>${STELAE_CONFIG_HOME}/.env.local"]
    EnvFiles[".env.example → ${STELAE_ENV_FILE}"]
    Renderers["scripts/render_* helpers<br/>(render_proxy_config.py, render_cloudflared_config.py, etc.)"]
    State["${STELAE_STATE_HOME}<br/>proxy.json · tool_overrides.json · tool_schema_status.json"]
    PM2["pm2 + long-lived daemons"]

    Templates --> Renderers
    LocalOverlays --> Renderers
    EnvFiles --> Renderers
    Renderers --> State
    State --> PM2
    LocalReset["Delete *.local file"] -.-> LocalOverlays
```

Templates remain read-only; every renderer merges the tracked default with the writable overlays and env layers before emitting runtime JSON into `${STELAE_STATE_HOME}` (the only path PM2 reads). Removing a `.local` file and rerendering immediately restores the tracked baseline.

### Core vs optional bundle

- **Tracked core:** custom tools, the Stelae integrator, the tool aggregator helper, the 1mcp stdio agent, and the public 1mcp catalog bridge (plus the Go proxy and FastMCP bridge). These five servers ship in `config/proxy.template.json` so every clone can immediately discover and manage downstream MCP servers, and the only aggregate that ships in git is the in-repo `manage_docy_sources` wrapper for `scripts/docy_manager_server.py`.
- **Starter bundle:** Docy + Docy manager, Basic Memory, Strata, Fetch, Scrapling, Cloudflared/worker helpers, filesystem/ripgrep/terminal controllers, and any other discovery-fed servers defined in `config/bundles/starter_bundle.json`. Install them (along with their overrides/aggregations) via `python scripts/install_stelae_bundle.py` so they only touch `${STELAE_CONFIG_HOME}/*.local.json`; this is the step that populates `workspace_fs_*`, `workspace_shell_control`, `memory_suite`, `doc_fetch_suite`, `scrapling_fetch_suite`, and `strata_ops_suite` in the local aggregator overlay. The Codex MCP wrapper intentionally lives outside this bundle to keep the default manifest lean—install it manually with `manage_stelae install_server` after you copy a wrapper release into `${STELAE_CONFIG_HOME}`.
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
    subgraph "Repo (git)"
        TO["config/tool_overrides.json"]
        TA["config/tool_aggregations.json"]
        MT["manifest.toolOverrides<br>(config/proxy.template.json)"]
    end

    subgraph "Overlays (${STELAE_CONFIG_HOME})"
        LO["tool_overrides.local.json"]
        LA["tool_aggregations.local.json"]
    end

    subgraph "Scripts & Helpers"
        PI["scripts/install_stelae_bundle.py"]
        PA["scripts/process_tool_aggregations.py"]
        TR["ToolOverridesStore.apply_overrides()"]
        RP["make render-proxy<br>→ scripts/process_tool_aggregations.py<br>→ scripts/render_proxy_config.py"]
    end

    subgraph "Runtime State (${STELAE_STATE_HOME})"
        RO["${TOOL_OVERRIDES_PATH}<br>(tool_overrides.json)"]
        RS["${TOOL_SCHEMA_STATUS_PATH}"]
        PC["${PROXY_CONFIG}<br>(proxy.json)"]
    end

    subgraph "PM2 runtime"
        Proxy["mcp-proxy (Go facade)"]
        AggSrv["tool_aggregator_server.py<br>(load_tool_aggregation_config)"]
    end

    subgraph "Downstream Servers"
        DS["Filesystem / rg / shell /<br>Docy / Fetch / Memory /<br>Strata / custom"]
    end

    subgraph "Client Surfaces"
        TL["(tools/list JSON)"]
        INIT["(initialize result)"]
        MAN["(manifest document)"]
        CL["╔══════════════╗<br>ChatGPT + Streamable clients"]
    end

    PI --> LO
    PI --> LA

    TO --> TR
    LO --> TR
    MT --> RP
    TR --> RO
    TR --> RS

    TA --> PA
    LA --> PA
    PA --> TR
    PA --> AggSrv

    RO --> RP
    RP --> PC
    PC --> Proxy

    Proxy -. stdio env .-> AggSrv
    DS -. stdio .-> Proxy
    AggSrv --> Proxy

    Proxy ==> |collectTools + overrides| TL
    Proxy ==> |collectTools + overrides| INIT
    Proxy ==> |"buildManifestDocumentWithOverrides()"| MAN

    TL --> CL
    INIT --> CL
    MAN --> CL
```

- **Authoring & overlays:** tracked JSON (`config/tool_overrides.json`, `config/tool_aggregations.json`, and the `manifest.toolOverrides` block inside `config/proxy.template.json`) define the baseline catalog. `scripts/install_stelae_bundle.py` and manual edits write contributor-specific layers into `${STELAE_CONFIG_HOME}/tool_overrides.local.json` and `${STELAE_CONFIG_HOME}/tool_aggregations.local.json`, keeping optional servers out of git.
- **Aggregation + overrides pipeline:**
  - `scripts/process_tool_aggregations.py` merges the tracked and local aggregation payloads via `load_tool_aggregation_config()` and emits two outputs: (1) transformed descriptors/`hiddenTools` entries that feed `ToolOverridesStore.apply_overrides()` and (2) the runtime definitions that `scripts/tool_aggregator_server.py` will read when the aggregate server starts.
  - `ToolOverridesStore` layers the manifest overrides (`manifest.toolOverrides`), the tracked template, and your `.local` overrides, then writes the resolved catalog to `${STELAE_STATE_HOME}/tool_overrides.json` (`${TOOL_OVERRIDES_PATH}`) plus schema metadata to `${TOOL_SCHEMA_STATUS_PATH}`. This step runs inside `make render-proxy` and also whenever `manage_stelae` installs/removes servers.
  - `scripts/render_proxy_config.py` embeds the resolved override path into `${STELAE_STATE_HOME}/proxy.json`, so pm2 and the restart helper always launch the proxy with the correct runtime file.
- **Runtime surfaces & responsibilities:**
  - `mcp-proxy` loads `${PROXY_CONFIG}`, launches every downstream server (including `tool_aggregator_server.py`), and calls `collectTools` to gather descriptors. Aggregate tools register themselves from the merged aggregation config; base servers (filesystem, ripgrep, shell, Docy, etc.) register via their native clients.
  - `buildManifestDocumentWithOverrides()` evaluates the same override set the JSON-RPC pipeline uses, so `/mcp/manifest.json`, the `initialize` response, and `tools/list` all share one resolver while still honouring transport-specific annotations.
  - Any server or tool marked `enabled:false` in either the tracked file or `.local` overlay is suppressed before descriptors reach clients. The proxy also annotates every exposed descriptor with `x-stelae` metadata that captures the primary and fallback servers, which is how troubleshooters map Codex observations back to the originating process.
- **Where to debug catalog drift:** when a tool disappears, check (in order) the overlay JSON under `${STELAE_CONFIG_HOME}`, the generated runtime files in `${STELAE_STATE_HOME}`, and the aggregator’s runtime config (`tool_aggregations.json` + `.local`). `scripts/run_e2e_clone_smoke_test.py --capture-debug-tools` snapshots each of these surfaces so we can compare the manifest/initialize/tools-list payloads Codex saw against the expected catalog.

## Operations & Troubleshooting

### Troubleshooting quick reference

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `mcp-proxy` not listening on `:${PROXY_PORT}` | Go build failed or pm2 stopped | `./scripts/run_restart_stelae.sh` or `source ~/.nvm/nvm.sh && pm2 restart mcp-proxy` |
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
        'STELAE_PROXY_BASE': f'http://127.0.0.1:{os.environ.get("PROXY_PORT", "9090")}',
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

- `scripts/run_e2e_clone_smoke_test.py` now provisions a throwaway workspace, installs the full starter bundle, seeds a Codex-friendly "client" repo, mirrors `~/.codex` into an isolated `CODEX_HOME`, drives `codex exec --json` through bundle/install/remove stages, and deletes any previously kept smoke sandboxes (`stelae-smoke-workspace-*` + `.stelae_smoke_workspace`) before creating a new one (unless `--reuse-workspace` is set). The script parses the JSONL transcripts and fails if required MCP calls (`workspace_fs_read`, `grep`, `doc_fetch_suite`, `manage_stelae`) are missing.
- Automatic runs cover the entire regression suite (`pytest tests/test_repo_sanitized.py` early, then the full suite + `make verify-clean` after Codex) and assert `git status` is clean after every managed install/remove. Use `--codex-cli`, `--codex-home`, `--workspace`, or `--wrapper-release` to tweak the sandbox inputs. Raw transcripts live under `${WORKSPACE}/codex-transcripts` for auditing.
- Pass `--manual` to drop back to the human-in-the-loop flow (the harness emits `manual_playbook.md` + `manual_result.json` and exits so a tester can run the mission in `dev/tasks/missions/e2e_clone_smoke.json`). Use `--manual-stage bundle-tools|install|remove` for stage-specific pause/resume, `--reuse-workspace` when resuming an existing sandbox, and `--cleanup-only [--workspace /path]` to retroactively delete kept workspaces without provisioning a new sandbox.
- **Testing rule of thumb:** keep the entire pytest/make suite clone-friendly. Any test that only works in the primary dev workspace must be clearly marked (e.g., pytest marker, separate make target) with rationale, and should never block the clone-focused harness. Default assumption: fresh clones run every regression test without modification.

### Tool aggregation helper

**Why:** Operators wanted a way to expose curated, high-level tools without duplicating logic across MCP servers or manually editing the overrides template. The aggregation helper keeps the catalog clean by letting us describe composites in JSON, hide the noisy downstream entries, and reuse the existing proxy infrastructure for dispatch.

**How it works:**

1. `config/tool_aggregations.json` declares each aggregate tool (manifest metadata, per-operation mappings, validation hints, and a `hideTools` list). The tracked file now contains only the suites that wrap in-repo servers (so far `manage_docy_sources`), while `${STELAE_CONFIG_HOME}/tool_aggregations.local.json` carries optional bundles and local overrides. The merged payload still obeys `config/tool_aggregations.schema.json` so CI / restart scripts can lint config changes early.
2. `scripts/process_tool_aggregations.py` runs during `make render-proxy` and the restart workflow. By default it executes the local scope, which looks only at `${STELAE_CONFIG_HOME}/tool_aggregations.local.json`, writes any user-defined aggregates into `${TOOL_OVERRIDES_PATH}`, and flips the corresponding `hideTools` entries to `enabled: false`. The tracked defaults in `config/tool_aggregations.json` are already reflected in `config/tool_overrides.json`; when those defaults change, rerun the script with `--scope default` and commit the result. The exporter also deduplicates JSON Schema `enum`/`required` arrays while merging data so repeated renders or local tweaks never surface invalid schemas to Codex.
3. `scripts/tool_aggregator_server.py` is a FastMCP stdio server launched by the proxy. On startup it registers one MCP tool per aggregation; at call time it validates the input per the declarative mapping rules, translates arguments into the downstream schema, and uses the proxy JSON-RPC endpoint to call the real tool. A custom `FuncMetadata` shim bypasses FastMCP’s argument marshalling so payloads are forwarded exactly as Codex sends them, and the runner now unwraps JSON-in-a-string responses before returning the downstream `content` blocks plus their original `structuredContent`. Response mappings (optional) can still reshape the downstream payload before returning to the client.
4. Because both the overrides and the stdio helper derive from the same config, adding a new aggregate requires zero Python changes—edit the JSON, run `make render-proxy`, and the proxy automatically restarts the helper with the new catalog.

Tracked suites declared in `config/tool_aggregations.json`:

- `manage_docy_sources` – Docy catalog manager (`list/add/remove/sync/import`), wrapping the in-repo `docy_manager` server.

After you install the starter bundle, `${STELAE_CONFIG_HOME}/tool_aggregations.local.json` adds the optional suites (`workspace_fs_read`, `workspace_fs_write`, `workspace_shell_control`, `memory_suite`, `doc_fetch_suite`, `scrapling_fetch_suite`, and `strata_ops_suite`) so third-party helpers continue to surface as a single aggregate entry without touching the tracked templates.

- `manage_docy_sources` – Docy catalog administration (list/add/remove/sync/import). The helper disables FastMCP’s schema conversion so `structuredContent` objects from the Docy manager flow straight back to Codex (no more JSON-in-a-string wrappers), and it automatically converts legacy string payloads into proper `TextContent` + dict responses.

If `tools/list` ever shrinks to the fallback `fetch`/`search` entries, the aggregator likely failed to register; rerun `make restart-proxy` (or `scripts/run_restart_stelae.sh --full`) to relaunch the stdio server and restore the curated catalog.

#### Aggregated Tool Formatting Flow

The request/response wiring below shows every component that touches the payload, along with the conditions that affect formatting. When we bypass FastMCP’s schema conversion we only skip redundant JSON parsing—the declarative argument and response mapping layers still enforce the schemas mirrored in `tool_overrides.json`.

```mermaid
flowchart LR
    A["Client (Codex / bridge)"] --> B["tool_aggregator handler"]
    B --> C["PassthroughFuncMetadata\n(no FastMCP arg validation/pre-parse)"]
    C --> D["AggregatedToolRunner.dispatch()"]
    D --> E["resolve_operation()\nselectorField + aliases"]
    E --> F{"requireAnyOf satisfied?"}
    F -- no --> G["ToolAggregationError\nreported upstream"]
    F -- yes --> H["_evaluate_rules(argumentMappings)\n• copy literals\n• drop null when stripIfNull\n• enforce 'required'"]
    H --> I["ProxyCaller → /mcp tools/call"]
    I --> J["Downstream server"]
```

```mermaid
flowchart LR
    J["Downstream server"] --> K["Proxy result\n(content + structuredContent)"]
    K --> L["_decode_json_like()\nrecursively parse JSON-looking strings"]
    L --> M{"responseMappings defined?"}
    M -- yes --> N["_evaluate_rules(responseMappings)\nproduces Aggregation result"]
    M -- no --> O{"structuredContent dict present?"}
    O -- yes --> P["structured_payload = structuredContent"]
    O -- no --> Q["structured_payload = None"]
    N --> R
    P --> R
    R --> S["_convert_content_blocks()\naccept dict/list/strings"]
    S --> T{"content blocks empty?"}
    T -- yes --> U["_fallback_text_block(pretty JSON)"]
    T -- no --> V["use downstream content"]
    U --> W["content = [TextContent]"]
    V --> W
    R --> X{"structured_payload exists?"}
    X -- yes --> Y["return (content, structured_payload)\nmatches tool_overrides outputSchema"]
    X -- no --> Z["return content only"]
```

Key takeaways:

- **Input path:** clients can send unparsed JSON strings (typical of some MCP agents). `PassthroughFuncMetadata` forwards them untouched, while the declarative `argumentMappings` still enforce required arguments and strip `null` values so downstream calls remain deterministic.
- **Output path:** every downstream response flows through `_decode_json_like` and `_convert_content_blocks`, guaranteeing that `structuredContent` remains a genuine object while the text block mirrors the payload. When `responseMappings` exist (e.g., to wrap results inside `{"result": {...}}`), the transformed dict is what the client receives; otherwise we reuse the downstream schema verbatim.
- **Tool overrides:** `ToolAggregationConfig.apply_overrides()` still updates `tool_overrides.json` with the aggregate’s `inputSchema`/`outputSchema`, so Codex sees descriptors that match the runtime behavior (tuple return when `structured_payload` exists, plain text when it does not).

- The proxy records per-tool adapter state in `${TOOL_SCHEMA_STATUS_PATH}` (path set through `manifest.toolSchemaStatusPath`) and patches `${TOOL_OVERRIDES_PATH}` whenever call-path adaptation selects a different schema (e.g., persisting generic for text-only servers). After rerunning `make render-proxy` + restarting PM2, external clients see the updated schemas. `scripts/populate_tool_overrides.py --proxy-url <endpoint> --quiet` now runs during `scripts/restart_stelae.sh` so every restart reuses the freshly collected `tools/list` payload to ensure all downstream schemas are persisted; the script still supports per-server scans for development via `--servers`, and operators can opt out entirely for a given restart with `--skip-populate-overrides`. When invoking manually, export `PYTHONPATH=$STELAE_DIR` so the helper can import `stelae_lib`.
- Facade fallback descriptors (`search`, `fetch`) remain available even if no downstream server supplies them, and they can also be overridden via the master block.

### Catalog publication & Codex trust boundaries

**Renderer → pm2 → proxy.** The catalog always originates from the rendered proxy config: `config/proxy.template.json:2-76` defines the Go facade address plus `toolOverridesPath`/`toolSchemaStatusPath` fields that point at `${STELAE_STATE_HOME}`. `scripts/render_proxy_config.py:18-78` loads layered `.env` values, guarantees `PROXY_PORT` is set (defaulting to `PUBLIC_PORT` or `9090`), and writes the merged JSON to `${PROXY_CONFIG}` (defaulting to `~/.config/stelae/.state/proxy.json`). Restarts (`scripts/run_restart_stelae.sh:41-139`) export that same `PROXY_PORT`, wait for the HTTP `/mcp` endpoint to report a minimum tool count, and immediately run `scripts/populate_tool_overrides.py` through the proxy so schema changes are captured in the config-home overlay. The clone-smoke harness keeps disposable sandboxes from clashing with the long-lived dev proxy by writing the randomly chosen `choose_proxy_port()` value into `.env`, `${STELAE_CONFIG_HOME}`, and the rendered proxy file inside `${STELAE_STATE_HOME}` (`stelae_lib/smoke_harness.py:54-122` plus docs/e2e_clone_smoke_test.md:89-124). Because `ecosystem.config.js:24-65` always launches pm2 with `${PROXY_CONFIG}` and defaults `STELAE_PROXY_BASE` to `http://127.0.0.1:9090`, any sandbox or developer environment that needs a different port must ensure both env vars are updated before restarts run.

#### Catalog rendering & publication flow

```mermaid
flowchart LR
    Aggregations["config/tool_aggregations*.json<br/>config/tool_overrides.json"] --> Process["scripts/process_tool_aggregations.py"]
    LocalOverrides["${STELAE_CONFIG_HOME}/tool_overrides.local.json"] --> Process
    Process --> StateOverrides["${STELAE_STATE_HOME}/tool_overrides.json"]

    ProxyTemplate["config/proxy.template.json"] --> RenderProxy["scripts/render_proxy_config.py"]
    EnvLayer["${STELAE_ENV_FILE} + ${STELAE_CONFIG_HOME}/.env.local"] --> RenderProxy
    RenderProxy --> ProxyConfig["${PROXY_CONFIG}"]

    ProxyConfig --> Restart["scripts/run_restart_stelae.sh<br/>pm2 ecosystem"]
    Restart --> Proxy["Go mcp-proxy"]
    Proxy --> Bridge["stelae_streamable_mcp\n(stdio)"]
    Proxy --> Tunnel["cloudflared tunnel\n(https://mcp.infotopology.xyz)"]
    Tunnel --> Remote["Remote clients (ChatGPT, etc.)"]
    Bridge --> Codex["Codex CLI / desktop IDEs"]

    Proxy --> Populate["scripts/populate_tool_overrides.py"]
    Populate --> LocalOverrides
    StateOverrides --> Proxy
```

Tracked + local overrides feed `process_tool_aggregations.py`, renderers materialize `${PROXY_CONFIG}`, the restart helper launches pm2 processes, and both FastMCP and Cloudflare consumers read the exact catalog that `/mcp` advertises. `populate_tool_overrides.py` completes the loop by snapshotting live schemas back into the overlay.

**Bridge + Codex trust.** The FastMCP bridge (`scripts/stelae_streamable_mcp.py:61-519`) acts as the stdio endpoint for Codex/VS Code. On startup it queries `PROXY_BASE` for `tools/list`, injects a local fallback descriptor for `manage_stelae` if the proxy catalog still lacks it, and monkey-patches FastMCP to forward `tools/list`, `tools/call`, prompts, and resources straight through to the Go facade. Codex only trusts the catalog it receives during `initialize`; even if `/mcp` and the TUI report the expected entries, an interactive session will continue using whatever tool list it cached earlier. That is why verifying the catalog requires creating a fresh Codex session each time the proxy restarts, rather than relying on `codex mcp` or curl probes alone.

**Verification loop.** Going forward we will treat the Codex MCP Wrapper automation as the “orchestrator” and `codex exec --json` sessions as disposable “testers.” The orchestrator (invoked through the `codex-wrapper-dev.batch` MCP tool) applies repo changes, renders configs, or restarts the stack; after every change it spawns a fresh Codex agent via `codex exec` so the tester can confirm the newly trusted catalog contains `stelae.manage_stelae`, `workspace_fs_read`, and the other must-have tools without out-of-band hints. Harness transcripts (`docs/e2e_clone_smoke_test.md:105-124`) already parse the bundle/install/remove stages, and this loop extends that coverage to catalog publication itself: if the tester ever falls back to CLI commands or reports “tool not found,” we know the proxy failed to advertise the entries during `initialize` and can bisect the issue immediately. The wrapper remains a separate MCP server (opt-in via `manage_stelae install_server`) so these trials never contaminate the default Stelae manifest.

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

- Remote clients traverse the Cloudflare tunnel; local clients use the FastMCP bridge (`scripts/stelae_streamable_mcp.py`).
- All paths share the same override-aware catalog inside the Go facade, guaranteeing consistent visibility between local and remote consumers.
- `manage_stelae` originates from the Go proxy manifest; the FastMCP bridge only injects a fallback descriptor (and short-circuits calls) if the proxy catalog is temporarily missing the tool. Once the proxy restarts cleanly, everything flows through the canonical manifest entry.

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
    A --▶|HTTP/SSE :${PROXY_PORT}| C
    C --▶|HTTPS| Public(("╔ChatGPT / Clients╗"))

    D --▶|diagnostic probes| C
    D --▶|pm2 restart| C

    Config["┌──────────────┐<br>${PROXY_CONFIG}"] --> A
    Overrides["┌──────────────┐<br>${TOOL_OVERRIDES_PATH}"] --> A
```

## Discovery & Auto-Loading Pipeline

0. Run `python scripts/bootstrap_one_mcp.py` after cloning. The helper clones or updates the forked `~/apps/vendor/1mcpserver`, runs `uv sync`, ensures `config/discovered_servers.json` exists, and writes a ready-to-use `~/.config/1mcp/mcp.json`. This keeps upstream repos read-only and makes discovery reproducible for every contributor.
1. The 1mcp agent watches the workspace and writes normalized descriptors to `config/discovered_servers.json` (one array of `{name, transport, command|url, args, env, tools, options}` objects). The file is tracked in git so proposed additions can be reviewed. The `discover_servers` operation in `manage_stelae` can also populate this cache directly, taking `query` + optional `tags`, `preset`, `limit`, and `min_score` filters. The results array echoes the fully normalised descriptors so operators can install them without a follow-up `list_discovered_servers` call. CLI folks can run `make discover-servers` (wrapper around `scripts/discover_servers_cli.py`) to drive the same operation via env vars when MCP isn’t involved.
2. During discovery the integrator applies catalog overrides for known slugs (for example Qdrant) so metadata-only entries gain runnable transport/command/env fields immediately. When an override introduces new env keys, the tool appends safe defaults to the writable env overlay (defaults to `${STELAE_CONFIG_HOME}/.env.local`, or the final `env_files` entry provided) so `${STELAE_ENV_FILE}`/`.env.example` stay generic yet installs succeed without manual edits.
3. `scripts/stelae_integrator_server.py` exposes the `manage_stelae` tool (and CLI) which loads the discovery cache, validates descriptors, and transforms them through three focussed helpers. The MCP bridge advertises the tool locally so Codex/clients call `stelae.manage_stelae` directly instead of shelling out:
   - `DiscoveryStore` normalises transports (`stdio`, `http`, `streamable-http`), cleans args/env, and flags incomplete entries.
   - `ProxyTemplate` ensures `config/proxy.template.json` gains sorted server stanzas, raising unless `force` is set when a duplicate exists.
   - `ToolOverridesStore` pre-populates `${STELAE_CONFIG_HOME}/tool_overrides.local.json` (and therefore `${TOOL_OVERRIDES_PATH}`) with descriptions and tool metadata so manifests stay descriptive from the first render.
4. After writing files (or emitting diffs during dry-runs) the integrator re-runs `make render-proxy` and `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared`, guaranteeing local parity (proxy + stdio bridge) even when operators lack Cloudflare credentials. Set `STELAE_RESTART_ARGS` to override those flags (for example `--full` to redeploy the tunnel + manifest). The tool waits for the proxy’s JSON-RPC health probes to succeed before returning.
5. Operations available through `manage_stelae`/CLI: `discover_servers`, `list_discovered_servers`, `install_server`, `remove_server`, `refresh_discovery`, and `run_reconciler`. Every response shares a single envelope containing `status`, `details`, `files_updated`, `commands_run`, `warnings`, and `errors` for easier automation.
6. Guardrails: commands referenced in descriptors must resolve on disk or via `.env` placeholders (`{{KEY}}`). The tool fails fast if binaries/vars are missing, before any template changes occur, and refuses to overwrite `.env.example` to keep the repo clone-friendly.

## Operational Notes

1. `make render-proxy` regenerates `${PROXY_CONFIG}` (defaults to `${STELAE_CONFIG_HOME}/proxy.json`), preserving the override file path. The pm2 ecosystem file (`ecosystem.config.js`) now uses the same default, so even long-lived daemons pick up the rendered overlay unless you explicitly set `PROXY_CONFIG` to a different path.
2. `bash scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` rebuilds the proxy, restarts PM2 processes, and validates the local JSON-RPC flow—this is the default path invoked by `manage_stelae`, keeping contributor laptops functional without requiring a tunnel. Append `--full` when you explicitly need to redeploy Cloudflare (manifest push + tunnel restart). The helper prints one-line `pm2 ensure <app>: status=<prev> -> <action>` entries so operators can see whether it started a missing process, deleted+started an unhealthy one, or simply refreshed an online entry.
3. `scripts/watch_public_mcp.py` shares the same `pm2 ensure` logic; when the public JSON-RPC probes fail it can now recreate `cloudflared` (delete+start) instead of looping on `pm2 restart`.
4. To temporarily hide a tool or server from clients, set `"enabled": false` via the overrides overlay (`${STELAE_CONFIG_HOME}/tool_overrides.local.json`) or template, rerun `make render-proxy`, then execute the restart script.

This document should serve as the reference for future diagnostics or enhancements to the catalog pipeline and transport topology.
