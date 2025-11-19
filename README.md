# Stelae MCP Stack

A WSL-native deployment of [mcp-proxy](https://github.com/TBXark/mcp-proxy) that exposes your local workspace to ChatGPT (and other MCP-aware agents) through a single HTTP/SSE endpoint. Everything runs on WSL, with an optional Cloudflare named tunnel for remote access.

---

## Stack Snapshot

| Component | Profile | Transport | Launch Command | Purpose |
|-----------|---------|-----------|----------------|---------|
| mcp-proxy | default | HTTP/SSE (:${PROXY_PORT:-9090}) | `${PROXY_BIN}` | Aggregates tools/prompts/resources from local MCP servers into one endpoint. |
| Filesystem MCP | local | stdio | `${FILESYSTEM_BIN} --root ${STELAE_DIR}` | Scoped read/write access to the repo. |
| ripgrep MCP | local | stdio | `${RG_BIN} --stdio --root ${SEARCH_ROOT}` | Code search backend powering the `grep` tool. |
| Commands MCP | local | stdio | `${NPX_BIN}` | Runs the `g0t4/mcp-server-commands` binary so terminal helpers execute inside the repo. |
| Tool aggregator MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/tool_aggregator_server.py` | Publishes declarative composite tools from config-home catalog fragments (`${STELAE_CONFIG_HOME}/catalog/*.json`) plus bundle fragments under `${STELAE_CONFIG_HOME}/bundles/*/catalog.json` (the starter bundle installs suites such as `workspace_fs_read`). |
| Stelae integrator MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/stelae_integrator_server.py` | Consumes 1mcp discovery output, updates templates/overrides, and restarts the stack via `manage_stelae`. |
| Basic Memory MCP | local | stdio | `${MEMORY_BIN}` | Persistent project memory. |
| Strata MCP | local | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing. |
| Fetch MCP | local | HTTP | `${LOCAL_BIN}/mcp-server-fetch` | Official MCP providing canonical `fetch`. |
| Scrapling MCP | local | stdio | `uvx scrapling-fetch-mcp --stdio` | Scrapling fetcher (basic/stealth/max-stealth), adapted by the Go proxy at call time. |
| FastMCP bridge | default | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Exposes the full proxy catalog to desktop agents; falls back to local search/fetch if the proxy is unavailable. Automatically loads `.env` / `${STELAE_CONFIG_HOME}/.env.local` so MCP adapters inherit the same runtime paths as pm2. |
| 1mcp agent | default | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovers nearby MCP servers and writes `${STELAE_DISCOVERY_PATH}` (defaults to `${STELAE_STATE_HOME}/discovered_servers.json`) for the integrator. |
| Custom tools MCP | default | stdio | `${PYTHON} ${STELAE_DIR}/scripts/custom_tools_server.py` | Config-driven wrapper that exposes scripts listed in `${STELAE_CONFIG_HOME}/custom_tools.json`. |

> The Go proxy we ship and test against lives in the [`Dub1n/mcp-proxy`](https://github.com/Dub1n/mcp-proxy) fork, which adds the streamable `/mcp` facade (HEAD/GET/POST) used by the restart script and smoke harness. Set `STELAE_PROXY_SOURCE` or pass `--proxy-source` if you need to pin a different remote; otherwise automation clones that fork automatically.

Path placeholders expand from `.env`; see setup below.

### Core vs Optional Stack

- **Core template:** the repo now ships only the self-management essentials (custom tools, the Stelae integrator, the tool aggregator helper, the 1mcp stdio agent, and the public 1mcp catalog bridge) plus the Go proxy and FastMCP bridge. Optional suites (workspace filesystem helpers, memory, fetch, etc.) appear only after installing the starter bundle so fresh clones stay lean.
- **Starter bundle:** Basic Memory, Strata, Fetch, Scrapling, filesystem/ripgrep/commands runners, and other developer-quality-of-life servers now live in the folder-based `bundles/starter/` package. `python scripts/install_stelae_bundle.py` copies that folder into `${STELAE_CONFIG_HOME}/bundles/starter/`, registers each server’s `installRef`, and runs `manage_stelae install_server` so catalog data flows through the bundle fragment instead of overlay files. Use `--server` to pick individual entries, `--dry-run` to preview the copy/install steps, or `--force` to overwrite an existing server entry when you rerun the installer.
- **Config-home only:** bundle installs copy folders into `${STELAE_CONFIG_HOME}/bundles/<name>/` and contribute catalog fragments there; removing the folder uninstalls it. No tracked overrides or `.local` files are touched.

### Overlay workflow & guardrails

Whenever you modify templates or catalog fragments, follow this loop so manifests stay deterministic and clone-safe:

1. `python scripts/process_tool_aggregations.py --scope local` – validate config-home catalog/bundle fragments and emit `${TOOL_OVERRIDES_PATH}` plus `${INTENDED_CATALOG_PATH}` under `${STELAE_STATE_HOME}`.
2. `make render-proxy` – re-render `${PROXY_CONFIG}` plus merged overrides inside `${STELAE_STATE_HOME}` (defaults to `${STELAE_CONFIG_HOME}/.state`).
3. `pytest tests/test_repo_sanitized.py` – fails if renders leak host-specific paths or stop pointing runtime outputs at the config/state homes.
4. `make verify-clean` (optional pre-commit step) – proves the render + restart helper leave `git status` empty.

Keep hand-edited config in `${STELAE_CONFIG_HOME}` (env files plus catalog fragments under `catalog/` and bundle folders under `bundles/`) and let renderers write runtime JSON into `${STELAE_STATE_HOME}` so machines never drift apart. The consolidated smoke-readiness plan in `dev/tasks/stelae-smoke-readiness.md` depends on this workflow; update that doc when process changes.

- Scrapling’s canonical schema lives in your config-home overrides (`${STELAE_CONFIG_HOME}/tool_overrides.json`) under the `scrapling` server. Both `s_fetch_page` and `s_fetch_pattern` advertise `{metadata, content}` payloads in the merged runtime file `${TOOL_OVERRIDES_PATH}`, and the Go proxy’s call-path adapter keeps those overrides in sync whenever a server emits a new structure. If Scrapling’s upstream contract changes, update the config-home file and rerun `make render-proxy` so manifests and tools/list remain truthful.

---

## Prerequisites

- Windows 11 + WSL2 (Ubuntu) with systemd enabled (`/etc/wsl.conf` → `[boot]` / `systemd=true`).
- Tooling installed: Go, Node.js + npm (via NVM), `pm2`, Python 3.11+, `pipx`, `ripgrep`, `cloudflared`.
- Discovery agent *(planned)*: `npm install -g @1mcp/agent` (provides the `1mcp` binary; integration TBD).
- Cloudflare named tunnel `stelae` with DNS `mcp.infotopology.xyz` and credentials stored under `~/.cloudflared/`.

---

## Environment & Config

1. Bootstrap the env file so `${STELAE_CONFIG_HOME}/.env` (exported as `STELAE_ENV_FILE`) becomes the canonical source of truth:
   ```bash
   python scripts/setup_env.py
   ```
   The helper copies `.env.example` into `${STELAE_ENV_FILE}` on first run, replaces `repo/.env` with a symlink (or copy when symlinks are unavailable) for backward compatibility, and with `--materialize-defaults` seeds `${STELAE_CONFIG_HOME}/catalog/core.json` using the embedded defaults so fresh clones immediately have a catalog fragment to edit.
2. Edit `${STELAE_ENV_FILE}` and update absolute paths:
   - Project roots: `STELAE_DIR`, `APPS_DIR`, `PHOENIX_ROOT`, `SEARCH_ROOT`.
   - Binaries: `FILESYSTEM_BIN`, `RG_BIN`, `MEMORY_BIN`, `STRATA_BIN`, `ONE_MCP_BIN`, `LOCAL_BIN/mcp-server-fetch`, `NPX_BIN` (runs `mcp-server-commands`).
   - Public URLs: `PUBLIC_BASE_URL=https://mcp.infotopology.xyz`, `PUBLIC_SSE_URL=${PUBLIC_BASE_URL}/stream`.
   - Local overlay home: `STELAE_CONFIG_HOME=${HOME}/.config/stelae`. User-edited config (`*.json`, `${STELAE_CONFIG_HOME}/.env.local`, discovery caches) lives here. Generated runtime artifacts (`${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${TOOL_SCHEMA_STATUS_PATH}`, etc.) live under `STELAE_STATE_HOME=${STELAE_CONFIG_HOME}/.state`, keeping the repo tidy—route any future runtime outputs there as well. Additional values appended by the integrator land in `${STELAE_CONFIG_HOME}/.env.local`; keep `${STELAE_ENV_FILE}` focused on human-edited keys.
   - Ports: `PROXY_PORT` controls where `mcp-proxy` listens locally; `PUBLIC_PORT` defaults to the same value so tunnels/cloudflared point to the correct listener. The clone smoke harness randomizes `PROXY_PORT` per workspace to avoid colliding with your long-lived dev stack, so keep these fields in sync.
3. Regenerate runtime config:
   \```bash
   make render-proxy
   \```
   This renders `${PROXY_CONFIG}` (defaults to `~/.config/stelae/.state/proxy.json`) from `config/proxy.template.json` using `${STELAE_ENV_FILE}` (plus `${STELAE_CONFIG_HOME}/.env.local` for hydrated defaults), so placeholders such as `{{ PATH }}` resolve correctly without pulling in fragile shell state.
4. (Optional) Tailor tool metadata with the config-home overrides (`${STELAE_CONFIG_HOME}/tool_overrides.json`). The file is validated against `config/tool_overrides.schema.json`, carries an explicit `schemaVersion`, and supports per-tool `description`, aliasing via `name`, richer annotation fields (including `title`), plus full `inputSchema`/`outputSchema` overrides so manifests always describe the wrapped payloads we return. The merged runtime file lives at `${TOOL_OVERRIDES_PATH}`, so keep the config-home copy focused on defaults you want locally:

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

  Declarative catalog fragments now live under `${STELAE_CONFIG_HOME}/catalog/*.json` plus `${STELAE_CONFIG_HOME}/bundles/*/catalog.json`. `scripts/process_tool_aggregations.py --scope local` (default) merges every fragment with the embedded defaults from `stelae_lib/catalog_defaults.py`, validates the merged payload against `config/tool_aggregations.schema.json`, writes `${TOOL_OVERRIDES_PATH}` just like before, **and** emits `${STELAE_STATE_HOME}/intended_catalog.json` with a timestamp and fragment metadata. The renderer now prefers `${STELAE_STATE_HOME}/live_descriptors.json`, fails fast if that snapshot is missing/stale unless you pass `--allow-stale-descriptors`, appends drift summaries to `${STELAE_STATE_HOME}/live_catalog_drift.log`, and updates `tool_schema_status.json` only when live descriptors are present (`--verify` also fails when the live catalog is missing unless drift is explicitly allowed). When you intentionally change the tracked defaults, rerun `python scripts/process_tool_aggregations.py --scope default`—that scope only reads `catalog/core.json` so your local overlays never bleed back into git. `make render-proxy` and `scripts/run_restart_stelae.sh` run the local scope automatically, and you can lint changes manually with `python scripts/process_tool_aggregations.py --check-only`. The stdio server `scripts/tool_aggregator_server.py` loads the merged catalog at runtime, bypasses FastMCP’s argument/output coercion so downstream payloads pass through unchanged, and now decodes JSON-in-a-string responses so `structuredContent` stays a real object while the text block mirrors the downstream summary. Bundle descriptors can also set `downstreamServer`; the aggregator forwards that value as `serverName` in every `tools/call`, so composites like `workspace_fs_read` continue to hit the real `fs` server even when overrides hide or rename the underlying tool. The end result is a concise manifest whose aggregates deliver the exact structured data that Codex (and the proxy) expect.

  `STELAE_USE_INTENDED_CATALOG=1` is now part of `.env.example`, so restarts prefer `${INTENDED_CATALOG_PATH}` and treat `${TOOL_OVERRIDES_PATH}` as a legacy fallback. Leave the flag at `1` for normal development—this guarantees docs/tests and the proxy read the same descriptor payload. When you truly need the old behavior (for example, while debugging a partial intended snapshot), set `STELAE_USE_INTENDED_CATALOG=0` in `${STELAE_CONFIG_HOME}/.env` or pass `--legacy-catalog` to `scripts/run_restart_stelae.sh`; `--intended-catalog` (or `--catalog-mode=intended|legacy`) flips it back without editing files. The restart helper logs which path was loaded, and the smoke harness mirrors the flag via `python scripts/run_e2e_clone_smoke_test.py --catalog-mode both` so CI can exercise legacy + intended flows before running Codex.

  After the proxy restarts and reports itself healthy, `scripts/restart_stelae.sh` invokes `scripts/capture_live_catalog.py` to snapshot the actual `/mcp tools/list` response into `${STELAE_STATE_HOME}/live_catalog.json`. The helper records the ISO8601 timestamp, proxy base, tool count, and the raw JSON-RPC payload so you can diff the intended catalog against what the proxy really advertised; renderer `--verify` now fails if this live snapshot is missing (unless drift is explicitly allowed), and drift deltas are appended to `${STELAE_STATE_HOME}/live_catalog_drift.log`. The restart script also runs `scripts/diff_catalog_snapshots.py` (best-effort) with `--fail-on-drift` to print missing/extra tool names after capture, `scripts/catalog_metrics.py` to emit a simple metrics JSON under `${STELAE_STATE_HOME}`, and `scripts/prune_catalog_history.py` to respect history limits. Run capture manually any time you need an updated snapshot (for example, after enabling a single stdio server) with:

  ```bash
  python scripts/capture_live_catalog.py --proxy-base http://127.0.0.1:9090
  ```

  Pass `--output` to capture into alternate files (handy for diffs) or set `STELAE_STATE_HOME`/`STELAE_PROXY_BASE` before invoking the script. The restart/verify automation already handles this, so `${STELAE_STATE_HOME}/live_catalog.json` is refreshed after every successful stack restart.

   After you install the starter bundle, the aggregator exposes these optional suites from the synced bundle catalog fragment:
   - `workspace_fs_read` – Read-only filesystem helpers (`list_*`, `read_*`, `find_*`, `search_*`, `get_file_info`, `calculate_directory_size`). Every operation explicitly targets the `fs` server via `downstreamServer`, so the aggregate keeps working even if the raw tool is hidden/renamed.
   - `workspace_fs_write` – Mutating filesystem helpers (`create_directory`, `edit_file`, `write_file`, `move_file`, `delete_*`, `insert_*`, `zip_*`, `unzip_file`). These operations also pin to `fs`, ensuring Codex never falls back to a missing `write_file` entry.
    > The filesystem server now launches with `rust-mcp-filesystem --allow-write {{STELAE_DIR}}`, so both read/write suites operate inside the repo. Pass absolute paths under `${STELAE_DIR}` when you need deterministic results—the binary inherits the proxy’s working directory, so relative paths depend on whichever cwd the proxy used when spawning the server.
  - `workspace_shell_control` – Workspace command helpers (`execute_command`, `change_directory`, `get_current_directory`, `get_command_history`) backed by `mcp-server-commands`, with cwd/history persisted under `${STELAE_STATE_HOME}` and injected automatically into each call. The aggregate always calls the `sh` server (`downstreamServer: "sh"`) so filtered manifests continue to work even if `run_command` is hidden.
   - `memory_suite` – All Basic Memory operations (context build, notes CRUD, project switches, searches).
  - `scrapling_fetch_suite` – Scrapling HTTP fetch modes (`s_fetch_page`, `s_fetch_pattern`).
  - `strata_ops_suite` – Strata orchestration (`discover_server_actions`, `execute_action`, `get_action_details`, `handle_auth_failure`, `search_documentation`).
  - (Reserved) Documentation/RAG catalog aggregate – will return once the vendor-neutral tooling is finalized.

   If `tools/list` ever collapses to the fallback `fetch`/`search` entries, restart the proxy (`make restart-proxy` or `scripts/run_restart_stelae.sh --full`) to respawn the aggregator server.

4. Proxy call-path adapter keeps flaky MCP servers usable without touching upstream code:
   - The Go proxy adapts tool call results at response time. Chain: pass-through → declared (uses `${TOOL_OVERRIDES_PATH}` and inline heuristics when the declared schema implies it) → generic `{ "result": "..." }`.
   - On success, the proxy updates `${TOOL_OVERRIDES_PATH}` atomically when the used schema differs (e.g., persists generic when no declared exists). It tracks runtime state in `${TOOL_SCHEMA_STATUS_PATH}` (path set via `manifest.toolSchemaStatusPath`).
   - This works for both stdio and HTTP servers and avoids inserting per-server shims.
5. Prime new servers’ schemas automatically: `scripts/restart_stelae.sh` now calls `scripts/populate_tool_overrides.py --proxy-url http://127.0.0.1:${PROXY_PORT}/mcp --quiet` after the local `tools/list` probe so freshly launched stacks immediately persist every tool’s `inputSchema`/`outputSchema` into `${STELAE_CONFIG_HOME}/tool_overrides.json` plus the merged `${TOOL_OVERRIDES_PATH}`. For ad-hoc use (e.g., focusing on a single stdio server), you can still run `PYTHONPATH=$STELAE_DIR ~/.venvs/stelae-bridge/bin/python scripts/populate_tool_overrides.py --servers fs` to launch that server directly, or hit any MCP endpoint with `--proxy-url` to reuse its catalog without re-spawning processes; append `--quiet` to either mode to suppress per-tool logs. When debugging and you truly need to skip the automatic write-back, pass `--skip-populate-overrides` to `scripts/run_restart_stelae.sh`.

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

The tracked templates stay lean on purpose. When you want Memory, Strata, Fetch, Scrapling, or the developer helpers (filesystem, ripgrep, commands runner), run the installer so they land in your `${STELAE_CONFIG_HOME}` overlays instead of git. (The Codex MCP wrapper intentionally lives outside this bundle—see the note below for the manual install flow.)

```bash
python scripts/install_stelae_bundle.py
```

- Add `--server docs --server fetch` to target specific servers, or omit `--server` to install everything described in `bundles/starter/`.
- Use `--dry-run` to preview the changes; `--no-restart` copies the bundle folder without touching PM2 (handy if the stack is already running elsewhere).
- The script copies `bundles/<name>/` into `${STELAE_CONFIG_HOME}/bundles/<name>/`, records install refs in `${STELAE_CONFIG_HOME}/bundle_installs.json`, ensures the bundle’s `catalog.json` fragment participates in the catalog merge, and then runs `make render-proxy` + `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` once so the new catalog is live immediately.
- **Codex MCP wrapper install (manual opt-in):**
  1. Build the wrapper release via `~/dev/codex-mcp-wrapper/scripts/build_release.py` and copy it into `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<version>` so `.env` can reference `CODEX_WRAPPER_BIN`/`CODEX_WRAPPER_CONFIG`.
  2. Save the descriptor below (update the `name` if you want a different label) as `/tmp/codex-wrapper.json`:

     ```json
     {
       "descriptor": {
         "name": "codex-wrapper",
         "transport": "stdio",
         "command": "{{CODEX_WRAPPER_BIN}}",
         "args": ["serve", "--config", "{{CODEX_WRAPPER_CONFIG}}"],
         "env": {"PYTHONUNBUFFERED": "1"},
         "options": {"displayName": "codex-wrapper"}
       }
     }
     ```

  3. Install it via the integrator CLI:

     ```bash
     python scripts/stelae_integrator_server.py --cli \
       --operation install_server \
       --params-file /tmp/codex-wrapper.json
     ```

  Keeping the wrapper out of `bundles/starter/catalog.json` prevents it from leaking into the default manifest; only run the steps above when you explicitly need the Codex automation stack.

Rerun the installer after pulling template updates or whenever you remove a bundle folder. Deleting `${STELAE_CONFIG_HOME}/bundles/<name>/` rolls the catalog back to the tracked core automatically.

### Config-home layout

Templates stay in `config/` (proxy, schemas), while writable data now lives only under `${STELAE_CONFIG_HOME}`:

- `${STELAE_CONFIG_HOME}/.env.local` receives hydrated secrets and generated values so `${STELAE_ENV_FILE}` stays portable.
- Catalog data lives in `${STELAE_CONFIG_HOME}/catalog/*.json` (seeded via `scripts/setup_env.py --materialize-defaults`) plus bundle fragments under `${STELAE_CONFIG_HOME}/bundles/*/catalog.json`; `process_tool_aggregations.py` merges these into `${TOOL_OVERRIDES_PATH}`/`${INTENDED_CATALOG_PATH}` inside `${STELAE_STATE_HOME}`.
- Other writable helpers (`tool_overrides.json`, `discovered_servers.json`, `custom_tools.json`, `tool_schema_status.json`) stay alongside the catalog directory in config-home. Renderers/helpers fail fast if these paths point outside `${STELAE_CONFIG_HOME}`/`${STELAE_STATE_HOME}`.
- Runtime caches (`${STELAE_DISCOVERY_PATH}`) and generated artifacts (`${PROXY_CONFIG}`, `${TOOL_OVERRIDES_PATH}`, `${TOOL_SCHEMA_STATUS_PATH}`, `${INTENDED_CATALOG_PATH}`) live under `${STELAE_STATE_HOME}` so git remains clean even when the proxy or integrator writes back metadata.
- Guardrail + baseline test: `require_home_path` enforces the config-home/state-home boundary for every mutable file. Keep `PYTHONPATH=. .venv/bin/pytest --ignore tests/test_e2e_clone_smoke.py` green (expected skips only) before shipping template/catalog changes.

### Hygiene Checks

- `pytest tests/test_repo_sanitized.py` fails if tracked configs reintroduce absolute `/home/...` paths or if `.env.example` stops pointing runtime outputs to `${STELAE_CONFIG_HOME}`. Run it whenever you touch templates to confirm renderers keep git clean.
- `make verify-clean` (wrapper around `scripts/verify_clean_repo.sh`) snapshots `git status --porcelain`, runs `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`, and then fails if any tracked files changed. Pass `VERIFY_CLEAN_RESTART_ARGS` or `./scripts/verify_clean_repo.sh --skip-restart` when you need to adjust the restart flow on machines without PM2/Cloudflared.

### Clone Smoke Test

- `python scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/<version>` now drives the entire clone gate automatically: it clones Stelae + `mcp-proxy`, installs the starter bundle, seeds a throwaway client repo for Codex, runs staged pytest/`make verify-clean`, and drives the `manage_stelae` install/remove cycle via `codex exec --json` while asserting `git status` stays clean between every step. Before provisioning a new sandbox it removes any prior smoke workspaces (directories matching `stelae-smoke-workspace-*` that contain `.stelae_smoke_workspace`) so stale sandboxes never accumulate unless you explicitly opt in to reusing one. The harness vendors `pytest` (and its deps) into `${WORKSPACE}/python-site` via `pip --target` so the structural test succeeds even when the host environment keeps `pip` locked behind `PIP_REQUIRE_VIRTUALENV`, and the bundle-stage prompt now tells Codex exactly which MCP tools to call even when the catalog forgets to list them—failed attempts are still valuable signal and must be recorded.
- The harness mirrors `~/.codex` into an isolated `${WORKSPACE}/codex-home` (override via `--codex-home`) and uses `--codex-cli` when you need to pin a specific binary. Codex transcripts for each stage land under `${WORKSPACE}/codex-transcripts/<stage>.jsonl`; the harness fails if the JSONL stream doesn’t include the expected tool calls (`workspace_fs_read`, `grep`, `manage_stelae`).
- Pass `--manual` to generate the full manual playbook/result files and exit immediately so a tester (or the Codex MCP wrapper mission) can follow the instructions outside the harness.
- Pass `--manual-stage bundle-tools|install|remove` to stop right before that Codex stage, emit `manual_stage_<stage>.md`, and exit. After completing the manual calls, rerun the harness with `--workspace <path> --reuse-workspace` (and without that `--manual-stage`) to continue.
- Use `--force-workspace` to overwrite an existing directory—even if it predates the marker file—or `--reuse-workspace` to keep the current sandbox intact between runs. Pair `--cleanup-only [--workspace /path]` with these flags to retroactively delete kept workspaces without rendering a new one.
- See `docs/e2e_clone_smoke_test.md` for prerequisites, CLI flags (`--workspace`, `--keep-workspace`, `--manual`, `--codex-cli`, `--codex-home`), and the Codex stage breakdown.
- Keep the regression suite clone-friendly: every pytest file and `make verify-*` target should succeed inside the sandbox the harness provisions. If you add a diagnostic that only makes sense on your primary dev machine, mark it clearly (e.g., pytest marker/skip, separate make target) and document why it can’t run in a fresh clone so the smoke test can skip it explicitly.

### Custom Script Tools

- `scripts/custom_tools_server.py` loads `${STELAE_CONFIG_HOME}/custom_tools.json` (override with `STELAE_CUSTOM_TOOLS_CONFIG`) and registers each entry as part of the `custom` stdio server now declared in `config/proxy.template.json`.
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

- After editing `${STELAE_CONFIG_HOME}/custom_tools.json`, rerun `make render-proxy` and restart the proxy via PM2 so the manifest reflects the new tools.
- Legacy connector-only fallbacks (`search`, `fetch`) are disabled via the config-home overrides file `${STELAE_CONFIG_HOME}/tool_overrides.json`, keeping the catalog limited to real servers and your custom scripts.

### Declarative Tool Aggregations

- The tracked proxy template keeps `tool_aggregator` enabled; catalog entries are sourced from `${STELAE_CONFIG_HOME}/catalog/*.json` plus `${STELAE_CONFIG_HOME}/bundles/*/catalog.json` and validated against `config/tool_aggregations.schema.json`. `scripts/process_tool_aggregations.py --scope local` merges those fragments with the embedded defaults, writes `${TOOL_OVERRIDES_PATH}`/`${INTENDED_CATALOG_PATH}`, and marks hidden tools as `enabled: false` so manifests stay tidy. Use `--scope default` only when you intentionally need to refresh the embedded defaults.
  A vendor-neutral documentation workflow is under construction; once the new aggregate (`documentation_catalog`) ships, it will surface here alongside the existing filesystem/memory/strata helpers.
- Aggregated tools return a tuple of downstream `content` blocks plus the preserved `structuredContent`. The runner skips FastMCP’s conversion layer (via a custom `FuncMetadata` shim) and unwraps JSON-like strings before replying, so Codex no longer sees serialized JSON blobs in the `structuredContent.result` field.
- To add another aggregate tool:

1. Copy the target block inside `bundles/starter/catalog.json` (or your `${STELAE_CONFIG_HOME}/catalog/*.json` fragment) and adjust the manifest metadata, `operations`, `argumentMappings`, `responseMappings`, and `hideTools` list for the downstream tool(s) you want to wrap.
 2. (Optional) Run `python scripts/process_tool_aggregations.py --check-only` to validate the JSON/schema without mutating overrides.
 3. Run `make render-proxy` (or `scripts/run_restart_stelae.sh`) so the helper refreshes `${TOOL_OVERRIDES_PATH}`, disables the wrapped tools, and restarts the `tool_aggregator` stdio server.
 4. Call the new MCP tool as normal (e.g., `tools/call name="documentation_catalog" arguments={...}` once it exists); arguments are validated per the rules you encode, then forwarded through the proxy to the downstream tool, and the downstream result is returned unchanged.

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

- Catalog overrides that hydrate descriptors (for example the Qdrant MCP) may require new environment keys. When `manage_stelae` encounters missing keys it appends safe defaults to your writable env overlay (default `${STELAE_CONFIG_HOME}/.env.local`, or the last `env` file you pass), keeping `.env.example` + `${STELAE_ENV_FILE}` generic for fresh clones.
- Supported operations:
  - `discover_servers` – Calls the vendored 1mcp catalogue to find candidates. Accepts `query`, `tags` (list or comma-separated), `preset`, `limit`, `min_score`, `append`, and `dry_run`. The response now echoes the matching descriptors under `details.servers` so you can immediately pick a `name` to install without running `list_discovered_servers`.
  - `list_discovered_servers` – Normalized entries + validation issues, helpful when vetting 1mcp output.
  - `install_server` – Accepts `name` (from discovery) or a full `descriptor` payload, optional `dry_run`, `force`, `target_name`, `options`, and `force_restart`.
  - `remove_server` – Removes template + override entries and restarts the stack (with `dry_run` previews available).
  - `refresh_discovery` – Copies `${ONE_MCP_DIR}/discovered_servers.json` (or a supplied `source_path`) into `${STELAE_DISCOVERY_PATH}`, returning a diff so you can see what changed.
  - `run_reconciler` – Re-runs `make render-proxy` + the restart script without touching configs; handy after manual template edits.
- For terminal-first workflows set the env overrides inline and call `make discover-servers`, e.g. `DISCOVER_QUERY="vector search" DISCOVER_LIMIT=5 DISCOVER_DRY_RUN=1 make discover-servers`. Supported env knobs mirror the MCP payload (`DISCOVER_QUERY`, `DISCOVER_TAGS`, `DISCOVER_PRESET`, `DISCOVER_LIMIT`, `DISCOVER_MIN_SCORE`, `DISCOVER_APPEND`, `DISCOVER_DRY_RUN`).
 - `manage_stelae` now ships in the proxy manifest like any other downstream server; the streamable bridge only injects a local fallback descriptor if the proxy catalog is missing the tool (for example during restart). Codex sessions keep working, but once the proxy is healthy all calls flow through the canonical manifest entry.
 - The tool reports file diffs, commands executed, proxy readiness waits, and warnings/errors in a uniform JSON envelope. All validations happen before any file writes so a missing binary or placeholder halts the operation early.
 - Manual override-only workflows remain supported via `python scripts/populate_tool_overrides.py --servers <name> --dry-run`, which refreshes schemas without consulting the discovery cache.
 - For non-MCP workflows you can inspect the catalogue directly via `scripts/one_mcp_discovery.py "vector search" --limit 10`, which uses the same backend as `discover_servers` and, unless `--dry-run` is set, merges the results into `${STELAE_DISCOVERY_PATH}`.
- Aggregated tools default their `outputSchema.type` to `"object"` to satisfy stricter clients (e.g., Codex MCP) that reject schema type arrays. If a client suddenly sees no Stelae tools, rerun `python scripts/process_tool_aggregations.py --scope local` plus `make render-proxy` to regenerate normalized descriptors.

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
    service: http://localhost:${PROXY_PORT:-9090}
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
  curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -skI https://mcp.infotopology.xyz/stream
   \```

---

## Local vs Remote Consumers

- Remote agents (e.g. ChatGPT) use the public manifest served via Cloudflare, which now mirrors the complete downstream tool catalog (annotations included).
- Local MCP clients can connect to `http://localhost:${PROXY_PORT:-9090}` and receive the same tool metadata, so overrides remain consistent between environments.
- **Codex CLI configuration:** To surface the aggregated tool catalog inside the Codex CLI/TUI, add a server entry to `~/.codex/config.toml` that launches the bundled FastMCP bridge. The key detail is that `STELAE_PROXY_BASE` must point at the bare proxy origin (`http://127.0.0.1:9090`) because the bridge automatically appends `/mcp` when it invokes JSON-RPC. A working snippet:

  ```toml
  [mcp_servers.stelae]
  command = "/home/gabri/.venvs/stelae-bridge/bin/python"
  args = ["-m", "scripts.stelae_streamable_mcp"]
  env = { "PYTHONPATH" = "/home/gabri/dev/stelae",
          "STELAE_STREAMABLE_TRANSPORT" = "stdio",
          "STELAE_PROXY_BASE" = "http://127.0.0.1:9090" }
  startup_timeout_sec = 30
  tool_timeout_sec = 180
  ```

  If the proxy handshake fails (for example, because the base URL mistakenly includes `/mcp` and the bridge hits `…/mcp/mcp`), the bridge drops into a minimal fallback that only exposes `search`/`fetch`. Always use the bare origin to keep the full aggregated catalog available in Codex.

---

## Future Developments

- Wire in the optional 1mcp discovery agent once the upstream contract settles *(not yet implemented)*.
- Decide whether to fully retire the legacy `scripts/stelae_search_mcp.py` shim now that the bridge mirrors the full catalog (track in TODO).

## Validation Checklist

1. `curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{tools: (.tools | map(.name))}'` shows the full downstream catalog (filesystem, ripgrep, shell, docs, memory, strata, fetch, etc.).
2. From ChatGPT, exercise `fetch` (canonical) and `rg/search` (ripgrep) to confirm both return JSON payloads.
3. `pm2 status` shows `online` for proxy, the FastMCP bridge, each MCP, and `cloudflared`.
4. Optional drift gate: `make check-catalog-drift` (or the best-effort diff from `scripts/restart_stelae.sh`) fails when intended vs live catalog diverge unless `STELAE_ALLOW_LIVE_DRIFT=1`; `make catalog-metrics` emits a JSON summary into `${STELAE_STATE_HOME}`; `make prune-catalog-history` prunes timestamped snapshots per env limits.

---

## Connector Readiness

- **Cloudflare tunnel up:** `pm2 start "cloudflared tunnel run stelae" --name cloudflared` (or `pm2 restart cloudflared`). `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` must return HTTP 200; a Cloudflare 1033 error indicates the tunnel is down. The watchdog (`scripts/watch_public_mcp.py`) now reuses the same `pm2 ensure` logic, so it can delete+start the tunnel automatically if the PM2 entry disappears.
- **Manifest sanity:** `curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'` verifies every essential MCP (filesystem, ripgrep, shell, docs, memory, fetch, strata, 1mcp).
- **SSE probes:** use the Python harness under `docs/openai-mcp.md` (or the snippets in this README) to connect to `/rg/sse` and `/fetch/sse`. Confirm `grep` returns results and `fetch` succeeds when `raw: true`.
- **Streamable HTTP bridge:** `scripts/stelae_streamable_mcp.py` now proxies the full catalog for local desktop agents; ensure the `stelae-bridge` pm2 process stays online. The bridge loads `.env`/`${STELAE_CONFIG_HOME}/.env.local` on startup so every MCP helper (e.g., `mcp__stelae__manage_stelae`) receives the same env vars the proxy uses.

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

Keep a backup of `~/.config/stelae/.state/proxy.json` (or rely on git history) before large changes.

---

## Troubleshooting

- `pm2 status` shows `Permission denied` → source NVM first (`source ~/.nvm/nvm.sh`).
- `search` missing in manifest → verify the bridge virtualenv has the required Python deps and restart the `stelae-bridge` pm2 process (`source ~/.nvm/nvm.sh && pm2 restart stelae-bridge`).
- `fetch` missing → ensure `mcp-server-fetch` lives under `${LOCAL_BIN}` and is executable.
- `jq: parse error` → wrap the jq program in single quotes: `jq '{servers, tools: (.tools | length)}'`.
- Cloudflare 404 on `/stream` → proxy offline or tunnel disconnected; inspect `pm2 logs mcp-proxy` and `pm2 logs cloudflared`.

---

## Related Files

- `config/proxy.template.json` — template rendered into `${STELAE_STATE_HOME}/proxy.json`.
- `scripts/render_proxy_config.py` — templating helper.
- `scripts/stelae_streamable_mcp.py` — FastMCP bridge that mirrors the proxy catalog for local clients.
- `scripts/stelae_search_mcp.py` — Legacy search shim kept for historical reference.
- `scripts/stelae_search_fetch.py` — HTTP shim (unused currently; keep for potential automation).
- `dev/server-setup-commands.md` — Cloudflare tunnel quick commands.
- `TODO.md` — backlog and future enhancements.
