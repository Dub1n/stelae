# Stelae MCP Stack

A WSL-native deployment of [mcp-proxy](https://github.com/TBXark/mcp-proxy) that exposes your local workspace to ChatGPT (and other MCP-aware agents) through a single HTTP/SSE endpoint. Everything runs on WSL, with an optional Cloudflare named tunnel for remote access.

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
| Tool aggregator MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/tool_aggregator_server.py` | Publishes declarative composite tools from `config/tool_aggregations.json` (e.g., `manage_docy_sources`). |
| Stelae integrator MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/stelae_integrator_server.py` | Consumes 1mcp discovery output, updates templates/overrides, and restarts the stack via `manage_stelae`. |
| Basic Memory MCP | stdio | `${MEMORY_BIN}` | Persistent project memory. |
| Strata MCP | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing. |
| Fetch MCP | HTTP | `${LOCAL_BIN}/mcp-server-fetch` | Official MCP providing canonical `fetch`. |
| Scrapling MCP | stdio | `uvx scrapling-fetch-mcp --stdio` | Scrapling fetcher (basic/stealth/max-stealth), adapted by the Go proxy at call time. |
| FastMCP bridge | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Exposes the full proxy catalog to desktop agents; falls back to local search/fetch if the proxy is unavailable. |
| 1mcp agent | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovers nearby MCP servers and writes `${STELAE_DISCOVERY_PATH}` (defaults to `~/.config/stelae/discovered_servers.json`) for the integrator. |
| Custom tools MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/custom_tools_server.py` | Config-driven wrapper that exposes scripts listed in `config/custom_tools.json`. |

Path placeholders expand from `.env`; see setup below.

### Core vs Optional Stack

- **Core template:** the repo now ships only the self-management essentials (custom tools, the Stelae integrator, the tool aggregator helper, the 1mcp stdio agent, and the public 1mcp catalog bridge) plus the Go proxy and FastMCP bridge. Every clone can immediately discover, install, and manage downstream servers without any extra steps.
- **Starter bundle:** Docy + Docy manager, Basic Memory, Strata, Fetch, Scrapling, and the developer-quality-of-life servers (filesystem, ripgrep, terminal controller) live in `config/bundles/starter_bundle.json`. Install them (and their overrides/aggregations) with `python scripts/install_stelae_bundle.py` after cloning. Use `--server` to pick individual entries or `--dry-run` to preview without touching overlays.
- **Overlays only:** the installer writes to `${STELAE_CONFIG_HOME}/config/*.local.json`, so optional services never reappear in tracked templates. Delete a `.local` file to return to the lean core stack, or rerun the installer if you need to rehydrate the bundle later.

- Scrapling’s canonical schema lives in the overrides template (`config/tool_overrides.json`) under the `scrapling` server. Both `s_fetch_page` and `s_fetch_pattern` advertise `{metadata, content}` payloads in the merged runtime file `${TOOL_OVERRIDES_PATH}`, and the Go proxy’s call-path adapter keeps those overrides in sync whenever a server emits a new structure. If Scrapling’s upstream contract changes, update the template or your local overlay and rerun `make render-proxy` so manifests and tools/list remain truthful.

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
   - Local overlay home: `STELAE_CONFIG_HOME=${HOME}/.config/stelae`. Automation writes `${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${STELAE_DISCOVERY_PATH}`, and `${TOOL_SCHEMA_STATUS_PATH}` into that directory so git never sees per-machine data. Additional values appended by the integrator land in `${STELAE_CONFIG_HOME}/.env.local`; keep the repo `.env` focused on human-edited keys.
2. Regenerate runtime config:
   \```bash
   make render-proxy
   \```
   This renders `${PROXY_CONFIG}` (defaults to `~/.config/stelae/proxy.json`) from `config/proxy.template.json` plus `config_home/proxy.template.local.json` if present. The renderer also merges `.env`, `.env.example`, and `${STELAE_CONFIG_HOME}/.env.local`, so placeholders such as `{{ PATH }}` resolve correctly without pulling in fragile shell state.
3. (Optional) Tailor tool metadata with the overrides template (`config/tool_overrides.json`). The file is validated against `config/tool_overrides.schema.json`, carries an explicit `schemaVersion`, and supports per-tool `description`, aliasing via `name`, richer annotation fields (including `title`), plus full `inputSchema`/`outputSchema` overrides so manifests always describe the wrapped payloads we return. The merged runtime file lives at `${TOOL_OVERRIDES_PATH}`; personal tweaks stay in `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json`, so keep the template focused on defaults that should ship with the repo:

   ```json
   {
     "schemaVersion": 2,
     "servers": {
       "fs": {
         "enabled": true,
         "metadata": {
           "description": "Filesystem helpers"
         },
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
       "tools": {
        "*": {
          "annotations": {}
        }
       }
     }
   }
   ```

   Each override lives under its originating server; the only legal `master.tools` entry is the wildcard `"*"` for global defaults. Setting `"enabled": false` at the server or tool level hides those entries from the manifest, `initialize`, and `tools/list` responses (and therefore from remote clients). Only the hints you specify are changed; unspecified hints keep the proxy defaults. Master-level renames are rejected on startup, and master-level description/title overrides emit a warning so you know global copy was applied.

   Aliases defined via `name` automatically flow through manifests, `initialize`, `tools/list`, and `tools/call`. Client requests using the alias are resolved back to the original downstream tool, while the original name remains available as a fallback for compatibility. The proxy annotates every `tools/list` entry with `"x-stelae": {"servers": [...], "primaryServer": "..."}` so automation (and the override population script) can map schemas back to the correct server without guessing.

   Declarative tool aggregations still use `config/tool_aggregations.json` (schema in `config/tool_aggregations.schema.json`), but the tracked template now only ships the stub definition plus the `facade.search` hide rule. Running `scripts/install_stelae_bundle.py` hydrates `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json` with the real aggregations. The helper `scripts/process_tool_aggregations.py` validates the merged file and writes descriptors directly to `${TOOL_OVERRIDES_PATH}` (without touching the template) so wrapped tools disappear from manifests. `make render-proxy` and `scripts/run_restart_stelae.sh` run the helper automatically, but you can lint changes manually with `python scripts/process_tool_aggregations.py --check-only`. The stdio server `scripts/tool_aggregator_server.py` reads the same config at runtime and exposes composite tools so the manifest stays concise.

   Current suites exposed by the aggregator (once the starter bundle installs the aggregation config + optional servers):
   - `workspace_fs_read` – Read-only filesystem helpers (`list_*`, `read_*`, `find_*`, `search_*`, `get_file_info`, `calculate_directory_size`).
   - `workspace_fs_write` – Mutating filesystem helpers (`create_directory`, `edit_file`, `write_file`, `move_file`, `delete_*`, `insert_*`, `zip_*`, `unzip_file`).
   - `workspace_shell_control` – Terminal controller helpers (`execute_command`, `change_directory`, `get_current_directory`, `get_command_history`).
   - `memory_suite` – All Basic Memory operations (context build, notes CRUD, project switches, searches).
   - `doc_fetch_suite` – Docy fetch helpers (`fetch_document_links`, `fetch_documentation_page`, `list_documentation_sources_tool`).
   - `scrapling_fetch_suite` – Scrapling HTTP fetch modes (`s_fetch_page`, `s_fetch_pattern`).
   - `strata_ops_suite` – Strata orchestration (`discover_server_actions`, `execute_action`, `get_action_details`, `handle_auth_failure`, `search_documentation`).
   - `manage_docy_sources` – Docy catalog management (list/add/remove/sync/import).

   If `tools/list` ever collapses to the fallback `fetch`/`search` entries, restart the proxy (`make restart-proxy` or `scripts/run_restart_stelae.sh --full`) to respawn the aggregator server.

4. Proxy call-path adapter keeps flaky MCP servers usable without touching upstream code:
   - The Go proxy adapts tool call results at response time. Chain: pass-through → declared (uses `${TOOL_OVERRIDES_PATH}` and inline heuristics when the declared schema implies it) → generic `{ "result": "..." }`.
   - On success, the proxy updates `${TOOL_OVERRIDES_PATH}` atomically when the used schema differs (e.g., persists generic when no declared exists). It tracks runtime state in `${TOOL_SCHEMA_STATUS_PATH}` (path set via `manifest.toolSchemaStatusPath`).
   - This works for both stdio and HTTP servers and avoids inserting per-server shims.
5. Prime new servers’ schemas automatically: `scripts/restart_stelae.sh` now calls `scripts/populate_tool_overrides.py --proxy-url http://127.0.0.1:9090/mcp --quiet` after the local `tools/list` probe so freshly launched stacks immediately persist every tool’s `inputSchema`/`outputSchema` into `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json` plus the merged `${TOOL_OVERRIDES_PATH}`. For ad-hoc use (e.g., focusing on a single stdio server), you can still run `PYTHONPATH=$STELAE_DIR ~/.venvs/stelae-bridge/bin/python scripts/populate_tool_overrides.py --servers fs` to launch that server directly, or hit any MCP endpoint with `--proxy-url` to reuse its catalog without re-spawning processes; append `--quiet` to either mode to suppress per-tool logs. When debugging and you truly need to skip the automatic write-back, pass `--skip-populate-overrides` to `scripts/run_restart_stelae.sh`.

6. Ensure the FastMCP bridge virtualenv (`.venv/` by default) includes `mcp`, `fastmcp`, `anyio`, and `httpx`:
   \```bash
   .venv/bin/python -m pip install --upgrade mcp fastmcp anyio httpx
   \```
   Install the fetch server with `pipx install mcp-server-fetch` if not already present.

   Install Scrapling MCP (optional, needed for high-protection sites):
   \```bash
   uv tool install scrapling-fetch-mcp
   uvx --from scrapling-fetch-mcp scrapling install
   \```

### Install the starter bundle

The tracked templates stay lean on purpose. When you want Docy, Memory, Strata, Fetch, Scrapling, the developer helpers (filesystem, ripgrep, terminal controller), or the Codex wrapper, run the installer so they land in your `${STELAE_CONFIG_HOME}` overlays instead of git:

```bash
python scripts/install_stelae_bundle.py
```

- Add `--server docs --server fetch` to target specific servers, or omit `--server` to install everything described in `config/bundles/starter_bundle.json`.
- Use `--dry-run` to preview the changes; `--no-restart` writes overlays without touching PM2 (handy if the stack is already running elsewhere).
- The script merges `tool_overrides.local.json` and `tool_aggregations.local.json`, then runs `make render-proxy` + `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` once so the new catalog is live immediately.
- To enable the optional Codex wrapper entry, first run `~/dev/codex-mcp-wrapper/scripts/build_release.py`. It creates a versioned release under `~/dev/codex-mcp-wrapper/dist/releases/<version>` (with wheel/sdist, checksums, `wrapper.toml`, and a ready-to-run `venv`). Publish that bundle (or copy it) into `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<version>` so the starter bundle can reference `CODEX_WRAPPER_BIN`/`CODEX_WRAPPER_CONFIG` via the defaults in `.env`.

Rerun the installer after pulling template updates or whenever you delete your local overlays. Removing `${STELAE_CONFIG_HOME}/config/proxy.template.local.json` reverts back to the five-server core automatically.

### Two-layer overlays

Every config file tracked in this repo is a template. Any local edits made via `manage_stelae`, the restart scripts, or manual tweaks are written to `${STELAE_CONFIG_HOME}` instead:

- `${STELAE_CONFIG_HOME}/.env.local` receives hydrated secrets and generated values so `.env` stays portable.
- `${STELAE_CONFIG_HOME}/config/*.local.json` mirrors the repo files (e.g., `proxy.template.local.json`, `tool_overrides.local.json`, `tool_aggregations.local.json`) and contains only your deviations.
- Renderers merge template → overlay → runtime (`${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${STELAE_CONFIG_HOME}/cloudflared.yml`, ...). Delete a `*.local.*` file and rerun the matching command to reset it.
- Runtime caches such as `${STELAE_DISCOVERY_PATH}` and `${TOOL_SCHEMA_STATUS_PATH}` already sit under `${STELAE_CONFIG_HOME}`, so git remains clean even when the proxy or integrator writes back metadata.

### Hygiene Checks

- `pytest tests/test_repo_sanitized.py` fails if tracked configs reintroduce absolute `/home/...` paths or if `.env.example` stops pointing runtime outputs to `${STELAE_CONFIG_HOME}`. Run it whenever you touch templates to confirm renderers keep git clean.
- `make verify-clean` (wrapper around `scripts/verify_clean_repo.sh`) snapshots `git status --porcelain`, runs `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`, and then fails if any tracked files changed. Pass `VERIFY_CLEAN_RESTART_ARGS` or `./scripts/verify_clean_repo.sh --skip-restart` when you need to adjust the restart flow on machines without PM2/Cloudflared.

### Clone Smoke Test

- `python scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/<version>` spins up a disposable workspace, clones both Stelae and `mcp-proxy`, writes an isolated `.env` (`STELAE_CONFIG_HOME`, `PM2_HOME`, Go caches, ports), runs `make render-proxy`, restarts the stack, and installs/removes `docy_manager` via the `manage_stelae` CLI while asserting `git status` stays clean.
- The harness publishes `manual_playbook.md` and `manual_result.json` inside the workspace so a human (or the Codex MCP wrapper) can repeat the same install/remove cycle through the real MCP transport. Update `manual_result.json` to `"status": "passed"` once the wrapper mission succeeds; the harness will exit with an error if the file is not updated.
- See `docs/e2e_clone_smoke_test.md` for prerequisites, CLI flags (`--workspace`, `--keep-workspace`, `--auto-only`), and the Codex wrapper mission flow.

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
- Legacy connector-only fallbacks (`search`, `fetch`) are disabled via the overrides template/overlay pair (`config/tool_overrides.json` + `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json`), keeping the catalog limited to real servers and your custom scripts.

### Docy Source Catalog

- **Optional module:** Docy and the Docy manager MCP live in the optional bundle. Disable them by removing the `docy*` entries from `${STELAE_CONFIG_HOME}/config/proxy.template.local.json`; their catalog overlays stay under `${STELAE_CONFIG_HOME}/config/docy_sources.local.json` so the tracked template remains a superset.
- `config/docy_sources.json` is the canonical list of documentation URLs. Each entry can carry `id`, `url`, `title`, `tags`, `notes`, `enabled`, and `refresh_hours` metadata so we can track provenance in git.
- `scripts/render_docy_sources.py` converts the catalog into `.docy.urls`, which Docy reads live on every request (no restart needed). The renderer writes comments next to each URL so operators know not to edit the generated file manually.
- The dedicated Docy manager MCP server (`scripts/docy_manager_server.py`) exposes the `manage_docy` tool. Operations cover `list_sources`, `add_source`, `remove_source`, `sync_catalog`, and `import_from_manifest`, mirroring the CLI mode (`python scripts/docy_manager_server.py --cli --operation add_source --params '{"url": "https://docs.crawl4ai.com/"}'`). The new importer can hydrate Docy in bulk from a JSON manifest (defaults to `${STELAE_DISCOVERY_PATH}`) or a remote MCP `.well-known` URL:

  ```bash
  python scripts/docy_manager_server.py --cli --operation import_from_manifest \
    --params '{"manifest_path": "${STELAE_DISCOVERY_PATH}", "tags": ["1mcp"], "dry_run": true}'
  ```

  When `dry_run` is `false` the catalog is saved and `.docy.urls` is re-rendered automatically; pass `manifest_url` instead of `manifest_path` to stream directly from a remote endpoint.
- Set `STELAE_DOCY_CATALOG` / `STELAE_DOCY_URL_FILE` if you relocate the catalog; otherwise defaults are `config/docy_sources.json` and `.docy.urls` at the repo root.

### Declarative Tool Aggregations

- **Optional server:** `tool_aggregator` only runs when you keep it enabled in `${STELAE_CONFIG_HOME}/config/proxy.template.local.json`. The repo template documents every available wrapper, while `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json` carries your custom copies so local-only stacks can pare down the catalog.
- `config/tool_aggregations.json` (validated by `config/tool_aggregations.schema.json`) describes composite MCP tools that we expose under the dedicated `tool_aggregator` server. Each entry defines manifest metadata plus a list of operations, and specifies which downstream tools should be hidden once the wrapper exists. `scripts/tool_aggregator_server.py` loads this file (plus `${STELAE_CONFIG_HOME}/config/tool_aggregations.local.json`) at runtime, while `scripts/process_tool_aggregations.py` writes the merged descriptors directly to `${TOOL_OVERRIDES_PATH}` and marks the `hideTools` entries as `enabled: false` so manifests stay tidy.
- `manage_docy_sources` wraps every Docy manager operation behind a single schema. Example payload:

  ```json
  {
    "operation": "import_from_manifest",
    "manifest_url": "https://mcp.example.com/.well-known/mcp/manifest.json",
    "dry_run": true,
    "tags": ["vendor:auto"]
  }
  ```

  The helper checks for required fields per operation (e.g., `url` for adds, `url` or `id` for removes, `manifest_path` or `manifest_url` for imports) before proxying the call to the original `manage_docy` tool.
- To add another aggregate tool:

 1. Copy the `manage_docy_sources` block inside `config/tool_aggregations.json` and adjust the manifest metadata, `operations`, `argumentMappings`, `responseMappings`, and `hideTools` list for the downstream tool(s) you want to wrap.
 2. (Optional) Run `python scripts/process_tool_aggregations.py --check-only` to validate the JSON/schema without mutating overrides.
 3. Run `make render-proxy` (or `scripts/run_restart_stelae.sh`) so the helper refreshes `${TOOL_OVERRIDES_PATH}`, disables the wrapped tools, and restarts the `tool_aggregator` stdio server.
 4. Call the new MCP tool as normal (e.g., `tools/call name="manage_docy_sources" arguments={...}`); arguments are validated per the rules you encoded, then forwarded through the proxy to the downstream tool, and the downstream result is returned unchanged.

### Bootstrapping the 1mcp catalogue

- Run `python scripts/bootstrap_one_mcp.py` after cloning this repo. The helper will:
  - clone or update `stelae-1mcpserver` under `${ONE_MCP_DIR:-~/apps/vendor/1mcpserver}`;
  - run `uv sync` inside the vendored repo (skip with `--skip-sync` if you manage deps elsewhere);
  - ensure `${STELAE_DISCOVERY_PATH}` exists so discovery output can be reviewed locally;
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
      "cachePath": "${STELAE_DISCOVERY_PATH}"
    }
  }
  ```

- Re-run the bootstrap script any time you relocate the repo or want to refresh the CLI config; use `--skip-update`/`--skip-sync` if you only need to rewrite the config file.

### Installing servers discovered by 1mcp

- 1mcp writes its discovery payload to `${STELAE_DISCOVERY_PATH}` (array of `{name, transport, command|url, args, env, description, source, tools, requiresAuth, options}` objects). Keep the repo template generic; local discoveries now live entirely under `${STELAE_CONFIG_HOME}`.
- The `manage_stelae` MCP tool is now served directly by the `stelae` bridge. Calls such as `tools/call name="manage_stelae"` stay connected even while the proxy restarts. Under the hood the tool updates templates/overrides and then runs `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared`, waiting for the proxy to come back before replying.
- When you need to redeploy the Cloudflare tunnel + worker, override the restart flags via `STELAE_RESTART_ARGS` (for example `STELAE_RESTART_ARGS="--keep-pm2 --no-bridge --full"` adds the manifest push + tunnel management back in).
- CLI examples (identical payload shape to the MCP tool):

  ```bash
  # Inspect discovery output
  python scripts/stelae_integrator_server.py --cli --operation list_discovered_servers

  # Preview a server install without writing files or restarting
  python scripts/stelae_integrator_server.py --cli --operation install_server \
    --params '{"name": "demo_server", "dry_run": true}'
  ```

- Catalog overrides that hydrate descriptors (for example the Qdrant MCP) may require new environment keys. When `manage_stelae` encounters missing keys it appends safe defaults to your writable env overlay (default `${STELAE_CONFIG_HOME}/.env.local`, or the last `env` file you pass), keeping `.env.example` + tracked configs generic for fresh clones.
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
- For non-MCP workflows you can inspect the catalogue directly via `scripts/one_mcp_discovery.py "vector search" --limit 10`, which uses the same backend as `discover_servers` and, unless `--dry-run` is set, merges the results into `${STELAE_DISCOVERY_PATH}`.

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

The helper script `scripts/run_restart_stelae.sh` wraps the full cycle (rebuild proxy, render config, restart PM2 fleet, optionally redeploy Cloudflare). For local-only parity run it with `--keep-pm2 --no-bridge --no-cloudflared` (the default invoked by `manage_stelae`) so the stack restarts cleanly even on laptops without a tunnel configured. Add `--full` when you explicitly want to push the manifest to Cloudflare KV and restart the named tunnel/worker. Each pm2 app now logs a one-line summary (e.g., `pm2 ensure cloudflared: status=errored -> delete+start`) so you can see exactly how the helper recovered missing or unhealthy entries.

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

- **Cloudflare tunnel up:** `pm2 start "cloudflared tunnel run stelae" --name cloudflared` (or `pm2 restart cloudflared`). `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` must return HTTP 200; a Cloudflare 1033 error indicates the tunnel is down. The watchdog (`scripts/watch_public_mcp.py`) now reuses the same `pm2 ensure` logic, so it can delete+start the tunnel automatically if the PM2 entry disappears.
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
