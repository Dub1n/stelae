# Clone Smoke Test (Codex MCP)

The clone smoke test proves that a fresh checkout can bootstrap the full stack, manage
servers via `manage_stelae`, and execute the same install/remove cycle through the
Codex MCP wrapper without touching your primary development environment.

## Prerequisites

- Go toolchain (for `mcp-proxy`), `pm2`, and `python3` available on `PATH`.
- Codex MCP wrapper release built via `~/dev/codex-mcp-wrapper/scripts/build_release.py`.
  Pass the path to `dist/releases/<version>` when running the harness so it can be
  mirrored into the sandbox (the folder must contain `venv/` and `wrapper.toml`).
- Network access to clone `https://github.com/TBXark/mcp-proxy.git`.

## Automated harness

Run the helper from the root of the primary repo. It clones Stelae + `mcp-proxy`
into a temporary workspace, writes a sandboxed `.env`, renders + restarts the stack,
and exercises the CLI side of `manage_stelae` (install/remove) while checking that
`git status` stays clean.

```bash
python scripts/run_e2e_clone_smoke_test.py \
  --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0
```

Key artifacts emitted inside the workspace:

| File | Purpose |
| --- | --- |
| `manual_playbook.md` | Human-readable instructions for the Codex phase. |
| `manual_result.json` | Template the tester must update to `status: "passed"` + notes. |
| `config-home/` | Disposable `${STELAE_CONFIG_HOME}` used by the sandbox. |
| `.pm2/` | Isolated PM2 state so the restart flow never collides with live processes. |

Common options:

- `--workspace /tmp/stelae-smoke` – reuse a specific directory (default is mktemp).
- `--keep-workspace` – keep the sandbox after success for further inspection.
- `--auto-only` – run the automated portion without waiting for the Codex phase.

## Manual Codex phase

With the harness paused, open `manual_playbook.md` inside the workspace. It walks
through the following steps:

1. `cd` into the sandbox clone and export `STELAE_CONFIG_HOME`/`PM2_HOME` pointing
   at the workspace paths that the harness printed.
2. Launch the Codex MCP wrapper using the copied release:
   ```
   ${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<ver>/venv/bin/codex-mcp-wrapper \
     run-mission dev/tasks/missions/e2e_clone_smoke.json \
     --workspace <sandbox> --config <wrapper.toml>
   ```
3. Inside Codex, call `manage_stelae` via the MCP catalog to install `docy_manager`
   under the alias `docy_manager_smoke`, verify the tool works, then remove it.
4. Record the call IDs and outcome in `manual_result.json` and set `"status": "passed"`.

Alternatively, follow the same steps manually via `tools/list` / `tools/call` if the
mission runner is unavailable. Either way, the harness will not continue until
`manual_result.json` reports success.

## Feedback + cleanup

After the Codex run finishes, return to the harness prompt, press `ENTER`, and it will:

1. Validate `manual_result.json` (fails if the status is still `pending`).
2. Kill the sandbox PM2 daemon.
3. Delete the workspace (unless `--keep-workspace` was set).

Rerun the script to repeat the cycle. Use `--keep-workspace` if you need to inspect
the generated overlays or PM2 logs after the smoke test.
