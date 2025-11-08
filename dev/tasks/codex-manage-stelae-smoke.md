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
