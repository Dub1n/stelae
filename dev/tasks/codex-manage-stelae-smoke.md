# Codex CLI Smoke Test – `manage_stelae`

Scenario: prove Codex CLI can run the full discovery → install flow using only the `stelae.manage_stelae` tool plus the helper wrappers that now live in this repo. Use this anytime the integrator changes, or before republishing the public manifest.

## Prerequisites

1. `. .venv/bin/activate` (or whichever venv you use for scripts) and `source ~/.nvm/nvm.sh` so PM2 + uv are on PATH.
2. Run the bootstrapper once after cloning (re-run if paths change):

   ```bash
   python scripts/bootstrap_one_mcp.py
   ```

   This guarantees `~/apps/vendor/1mcpserver` exists, `uv sync` ran, `config/discovered_servers.json` is tracked, and `~/.config/1mcp/mcp.json` points at the vendored repo.
3. Ensure the stack is healthy: `make render-proxy && make restart-proxy` (or `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`).
4. Launch Codex CLI pointing at the streamable proxy (`codex --profile stelae`). Confirm `tools/list` shows the synthetic `manage_stelae` entry.

## Golden-path flow

1. **Discover candidates** (Codex `tools/call`). Send:

   ```json
   {
     "name": "manage_stelae",
     "arguments": {
       "operation": "discover_servers",
       "params": {
         "query": "vector search",
         "tags": ["search"],
         "limit": 5,
         "dry_run": true
       }
     }
   }
   ```

   Expected: `status: ok`, `details.servers[*].descriptor` hydrated, `files_updated[0].dryRun` set. Capture one of the returned `name` fields for the next step.
2. **Dry-run install** to preview diffs without touching files:

   ```json
   {
     "name": "manage_stelae",
     "arguments": {
       "operation": "install_server",
       "params": {
         "name": "<server-from-step-1>",
         "dry_run": true
       }
     }
   }
   ```

   Expected: the template/override diffs render under `files_updated`, `commands_run` is empty.
3. **Real install** (same payload with `"dry_run": false`). The tool streams logs while it executes `make render-proxy` and `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`, then waits for the proxy readiness probe before replying. `commands_run[*].status` should all be `ok`.
4. **Optional reconciler / removal**: send `{"operation": "run_reconciler"}` to confirm restart automation works without edits, or `{"operation": "remove_server", "params": {"name": "<server>"}}` to validate cleanup.

## Verification commands

- Local CLI parity: `DISCOVER_QUERY="vector search" DISCOVER_LIMIT=5 DISCOVER_DRY_RUN=1 make discover-servers` should mirror what Codex returns.
- Cache diff: `python scripts/stelae_integrator_server.py --cli --operation list_discovered_servers | jq '.details.servers[0]'` verifies descriptors were persisted.
- Manifest check: `curl -s http://localhost:9090/.well-known/mcp/manifest.json | jq '.tools[] | select(.name == "manage_stelae")'` confirms the tool remains advertised after restart.

## Cleanup

- Remove any demo servers you installed: `python scripts/stelae_integrator_server.py --cli --operation remove_server --params '{"name": "<server>"}'`.
- Re-run `python scripts/bootstrap_one_mcp.py --skip-update --skip-sync` if you relocate repos so the CLI config stays accurate.

## 2025-11-08 Run Notes

- `stelae.manage_stelae` *does* answer via MCP/Codex: `mcp__stelae__manage_stelae({"operation":"discover_servers","params":{"query":"vector search","tags":["search"],"limit":5,"dry_run":true}})` returned `status: ok`, appended five entries, and echoed the descriptors under `details.servers[*].descriptor`. `files_updated[0]` shows `changed: false` because the cache already contained those metadata stubs.
- Every discovery result is still `transport: "metadata"` with neither `command` nor `url`, so step 2 (install by `name`) fails immediately with `"stdio descriptor missing command"`. We need either (a) richer descriptors from 1mcp, or (b) a follow-up step that hydrates the descriptor before calling `install_server`.
- Because install/remove cannot proceed past the validation, the remainder of the golden path (dry-run diffs, restart orchestration, real install) is still blocked. Once a descriptor includes concrete transport details, re-run from step 2.

### Follow-up plan (completed 2025-11-08)

- [x] `discover_servers` now hydrates descriptors inline via the override catalog (`stelae_lib/integrator/catalog_overrides.py:5-43`) and writes placeholder env defaults so installs no longer fail validation.
- [x] The full smoke loop (discover → dry-run install → real install → reconciler/removal) was rerun successfully; see the detailed run immediately below plus regression coverage in `tests/test_stelae_integrator.py:147-214`.

### 2025-11-08 Hydration + Smoke Upgrade

- `discover_servers` now applies a catalog override for the `qdrant` slug. Returned descriptors include `transport: "stdio"`, `command: "uvx"`, and args/env placeholders (`COLLECTION_NAME`, `QDRANT_LOCAL_PATH`, `EMBEDDING_MODEL`). The overrides are tracked in `stelae_lib/integrator/catalog_overrides.py`, with new `.env` defaults for the placeholders.
- Codex MCP runs (all via `mcp__stelae__manage_stelae`):
  1. **Discover (dry-run)** – confirmed hydrated descriptor surfaced in `details.servers[*].descriptor` (qdrant shows stdio + command/args/env). `files_updated` stayed `dryRun:true`.
  2. **Discover (real)** – same payload with `"dry_run": false` persisted the hydrated entry to `config/discovered_servers.json`.
  3. **Install (dry-run)** – `{"operation":"install_server","params":{"name":"qdrant","dry_run":true}}` produced the expected diffs for `config/proxy.template.json` and `config/tool_overrides.json`.
  4. **Install (real)** – the first execution completed server-side (logs show `qdrant` tools registering) but the MCP response dropped when `run_restart_stelae.sh` restarted the proxy. A follow-up install (no changes, so no restart) returned `status: ok` to capture the final state.
  5. **Remove (dry-run + real)** – verified diffs, then removed the server. As with install, the real removal restarts the stack and drops the in-flight response; after the restart we brought `mcp-proxy` back via pm2 and confirmed the template/overrides were clean.
- `DISCOVER_QUERY="vector search" ... make discover-servers` mirrors the MCP output and now shows `qdrant` as `status: "cached"` with the hydrated descriptor embedded in the cache.
- Known behavior: real installs/removals currently sever the Codex MCP request when the proxy restarts; rerunning the tool after the stack is back online confirms the final state, and pm2 restarts are required to resume service. **Resolved 2025-11-10:** `scripts/stelae_streamable_mcp.py:519-547` now short-circuits every `manage_stelae` call to the local `StelaeIntegratorService`, so bridge-driven installs/removals stay connected even while the Go proxy restarts.

### 2025-11-09 Restart Validation

- Command: `source ~/.nvm/nvm.sh && scripts/run_restart_stelae.sh --no-bridge --full`. Letting the helper own pm2 (no `--keep-pm2`) avoided the “Process not found” errors seen when restarting partially-stopped apps.
- Local verification:
  - `curl -s http://127.0.0.1:9090/.well-known/mcp/manifest.json | jq '{toolCount: (.tools|length)}'` → `toolCount: 71`.
  - Sample tools: `manage_stelae`, `s_fetch_page`, `rg`, `docy`, `filesystem`, etc.
- Public verification:
  - `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq '{toolCount: (.tools|length), sample: (.tools|map(.name)[0:10])}'` → 60 tools, sample `[build_context, calculate_directory_size, canvas, change_directory, create_directory, create_memory_project, delete_file_content, delete_note, delete_project, directory_tree]`.
- pm2 after the run:

  ```bash
  $ source ~/.nvm/nvm.sh && pm2 status
  ┌────┬──────────────┬────────────┬─────────┬─────────┬──────────┐
  │ id │ name         │ pid        │ status  │ cpu     │ mem      │
  ├────┼──────────────┼────────────┼─────────┼─────────┼──────────┤
  │ 0  │ mcp-proxy    │ 809110     │ online  │ 0%      │ 15.9mb   │
  │ 1  │ watchdog     │ 809181     │ online  │ 0%      │ 21.9mb   │
  │ 2  │ cloudflared  │ 809378     │ online  │ 0%      │ 53.6mb   │
  │ 3  │ stelae-bridge│ 809893     │ online  │ 0%      │ 6.8mb    │
  └────┴──────────────┴────────────┴─────────┴─────────┴──────────┘
  ```

- Next action: bake these commands into the smoke checklist (and keep the `--no-bridge` flag noted so Codex operators know why the bridge may briefly disconnect during maintenance).
