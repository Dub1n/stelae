# Clone Smoke Test (Codex MCP)

The clone smoke test proves that a fresh checkout can bootstrap the entire stack,
install/remove managed servers, and survive a full Codex MCP session without touching
an engineer's primary development environment. The harness now runs Codex in
non-interactive mode via `codex exec --json`, records every MCP tool call, and fails if
expected calls (starter bundle tools + `manage_stelae`) are missing.

## Prerequisites

- Go toolchain (for `mcp-proxy`), `pm2`, and Python 3.11+ on `PATH`.
- Codex CLI installed and logged in. The harness mirrors `~/.codex` into the sandbox
  unless you override the path with `--codex-home`.
- Optional: Codex MCP wrapper release (built via
  `~/dev/codex-mcp-wrapper/scripts/build_release.py`). Pass
  `--wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/<version>` so the starter
  bundle can copy the release in alongside the clone.
- Network access to clone `https://github.com/TBXark/mcp-proxy.git` and fetch any MCP
  servers Codex exercises.

## Automated harness

Run the helper from the repo root:

```bash
python scripts/run_e2e_clone_smoke_test.py \
  --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 \
  --codex-cli $(which codex)
```

The harness will:

1. Clone Stelae + `mcp-proxy` into a disposable workspace, create an isolated `.env`,
   and install the entire starter bundle (using `--no-restart`) so filesystem/rg/Strata/etc. are
   available before Codex connects. Restarts happen in the next step so the harness can stream the
   log output directly.
2. Seed a tiny "client" git repo next to the clone so `codex exec` can run inside a
   clean working tree while MCP calls operate on the clone itself.
3. Automatically delete any prior smoke workspaces it finds (directories that start
   with `stelae-smoke-workspace-` and contain `.stelae_smoke_workspace`) before
   provisioning a new one, and mirror `~/.codex` (or `--codex-home`) into
   `${WORKSPACE}/codex-home` while exporting `CODEX_HOME`/`CODEX_API_KEY`.
4. Run staged tests: `pytest tests/test_repo_sanitized.py` immediately after render,
   then the full pytest suite + `make verify-clean` after the Codex cycle so the smoke
   test doubles as the clone gate. The harness now bootstraps a disposable
   `python-site/` inside the workspace, installs `pytest` there via `pip --target`,
   and temporarily disables `PIP_REQUIRE_VIRTUALENV` so developers that enforce that
   guardrail on their host still get a working structural check.
5. Drive Codex through three JSONL stages (bundle tools, install Qdrant as
   `qdrant_smoke`, remove it again). Each stage runs `codex exec --json --full-auto`
   with scripted instructions and writes the transcript to
   `${WORKSPACE}/codex-transcripts/<stage>.jsonl`. The harness parses the JSON lines
   and fails if it cannot find the required `workspace_fs_read`, `grep`,
   or `manage_stelae` calls.
6. Assert `git status --porcelain` is empty after every major step (bundle install,
   Codex install/remove, final tests).

Key artifacts in the workspace:

| Path | Purpose |
| --- | --- |
| `config-home/` | Disposable `${STELAE_CONFIG_HOME}` (env overlays, tool overrides, runtime caches). |
| `.pm2/` | Isolated PM2 home so restarts do not collide with your main stack. |
| `codex-home/` | Mirrored `CODEX_HOME` (config + auth). |
| `client-repo/` | Minimal git repo used as the Codex working tree. |
| `codex-transcripts/*.jsonl` | Raw `codex exec --json` streams per stage. |
| `manual_playbook.md` / `manual_result.json` | Only created when `--manual` is set (see below). |

When `--capture-debug-tools` is set the harness also writes `streamable_tool_debug.log` and
`tool_aggregator_debug.log` snapshots into `${WORKSPACE}/logs/` (named `<stage>-*.log`), copies the same files into
`codex-transcripts/`, and mirrors each snapshot back to `dev/logs/harness/<timestamp>-<stage>-*.log` so the evidence
survives even if the disposable workspace is deleted.

For the active backlog, run logs, and troubleshooting playbooks see
`dev/tasks/stelae-smoke-readiness.md`.

Common options:

- `--workspace /tmp/stelae-smoke` – reuse a specific directory instead of `mkdtemp`.
- `--keep-workspace` – keep artifacts after success.
- `--codex-cli /path/to/codex` – pin a specific Codex binary (defaults to `shutil.which("codex")`).
- `--codex-home /path/to/.codex` – mirror a custom Codex config/auth directory into the sandbox.
- `--wrapper-release …` – copy a Codex MCP wrapper release into the sandbox so the starter bundle can expose it.
- `--proxy-source <git-or-path>` – override the mcp-proxy checkout source. When omitted the harness checks `STELAE_PROXY_SOURCE`, then falls back to a local `~/apps/mcp-proxy` clone (useful when hacking on the fork), and finally clones `https://github.com/Dub1n/mcp-proxy.git`, which contains the `/mcp` facade required for the readiness probes.
- `--manual` – generate `manual_playbook.md` / `manual_result.json`, then exit immediately so you can follow the instructions manually. The harness still provisions the sandbox (clone, bundle install, restart) so the manual steps have a ready workspace; this flag simply skips the Codex automation that would normally follow.
- `--manual-stage bundle-tools|install|remove` – stop right before a specific Codex stage, emit `manual_stage_<stage>.md`, and exit. After finishing those steps, rerun with `--workspace <path> --reuse-workspace` (and without that `--manual-stage`) to continue.
- `--capture-debug-tools` – enable the FastMCP/tool-aggregator debug env vars, store their log files under `${WORKSPACE}/logs/`,
  add a per-stage copy to `codex-transcripts/`, and mirror the same snapshots to `dev/logs/harness/` so the artifacts survive
  even when the disposable workspace is deleted.
- `--bootstrap-only` – run the clone/bundle/bootstrap steps once, keep the workspace, and exit before restarting the stack. Pair with `--workspace … --keep-workspace` (set automatically) so subsequent runs can reuse the warmed caches.
- `--skip-bootstrap --workspace <path> --reuse-workspace` – reuse a previously prepared smoke workspace without re-running clone/bundle setup. The harness validates that `.env`, the proxy checkout, and the workspace marker still exist, then keeps the previously assigned `PROXY_PORT` so reruns exercise the same install phase without repeating dependency downloads.
- `--restart-timeout <seconds>` – bound each `run_restart_stelae.sh` invocation (default 90 s). When the timeout fires, the harness dumps `pm2 status`, tail snippets from `${PM2_HOME}/logs/*`, and retries up to `--restart-retries`.
- `--restart-retries <count>` – number of additional restart attempts after a timeout (default 1). Each attempt restreams the helper logs so you can tell whether pm2 made progress.
- `--heartbeat-timeout <seconds>` – abort the run if no log output arrives within the given window (default 240 s). Heartbeat exits collect the same diagnostics as restart timeouts so Codex sessions never sit silently for minutes.

**Important:** The “install” phase (starter bundle + `make render-proxy` + restart script) consistently completes in under one minute on a clean sandbox. If you see the harness stuck on “Installing starter bundle…” or “Restarting stack…”, treat it as an orchestration failure—use `--restart-timeout`, `--restart-retries`, and `--heartbeat-timeout` to bail out quickly, capture the pm2/log snippets, and debug the blocked subprocess instead of raising the timeout ceiling.
- `--force-workspace` – overwrite the directory passed to `--workspace` even if it predates the harness marker or contains other files. Recommended when you want deterministic paths plus full logs (pair with `--keep-workspace`).
- `--reuse-workspace` – reuse an existing smoke workspace (identified by `.stelae_smoke_workspace`) instead of deleting it. Required when resuming a manual stage; pair with `--workspace <path>`.
- `--cleanup-only [--workspace /path]` – delete previously kept smoke workspaces (or a specific path) and exit without provisioning a new clone.

### Port selection & graceful shutdown

- Every workspace picks a randomized high `PROXY_PORT`/`PUBLIC_PORT` via `choose_proxy_port()` and exports the value through `.env`, `${STELAE_CONFIG_HOME}`, and the rendered `proxy.json`. This keeps disposable sandboxes from binding to the developer’s long-lived `:9090` proxy.
- Before the restart script runs, the harness preflights the chosen port: it inspects `ss`/`lsof`, sends `SIGTERM`/`SIGKILL` to any lingering listeners, and rechecks so pm2 never collides with a stale proxy. Expect to see `[port-preflight]` logs whenever an old process is cleaned up.
- The renderer now substitutes `{{PROXY_PORT}}` inside `config/proxy.template.json`, so pm2 always starts `mcp-proxy` on the sandbox-specific port. Local `.env` files should keep `PROXY_PORT` and `PUBLIC_PORT` synchronized; in most setups both remain `9090`.
- `ecosystem.config.js` defaults `PROXY_CONFIG` to `${STELAE_STATE_HOME}/proxy.json` (and `${STELAE_STATE_HOME}` falls back to `${STELAE_CONFIG_HOME}/.state`), which is the same file the harness renders inside the config home. This ensures pm2 restarts (even when the daemon survives across runs) keep honoring the sandbox port. When reusing a workspace created before this change, copy the updated `ecosystem.config.js` into the sandbox or rerun the bootstrap step so pm2 stops falling back to the repo path.
- `scripts/process_tool_aggregations.py --scope local` refreshes only the user-defined aggregates under `${STELAE_CONFIG_HOME}` before exporting `${TOOL_OVERRIDES_PATH}`, and the exporter deduplicates JSON Schema `enum`/`required` arrays. The tracked template intentionally ships empty, so installing the starter bundle is what writes the filesystem/memory/strata wrappers into your overlay. Re-run the script (it is part of `scripts/run_restart_stelae.sh`) if `tools/list` starts showing the raw filesystem tools or Codex complains about repeated `operation` fields—those symptoms mean the manifest is still reading a stale override file. When default aggregates change, run `python scripts/process_tool_aggregations.py --scope default` once, commit the updated `config/tool_overrides.json`, and let `make render-proxy` pick it up.
- Sending `Ctrl+C` (SIGINT) or SIGTERM to the harness triggers the new graceful shutdown handler: it kills the sandbox PM2 daemon (respecting `PM2_HOME`), cleans up the workspace when `--keep-workspace` is not set, and exits with status 130/143. This prevents stray processes from lingering if a run is aborted mid-restart.
- Restart/heartbeat timeouts automatically dump `pm2 status` plus tail snippets from `${PM2_HOME}/logs/*` so Codex transcripts always have the context needed to debug hanging restarts.

### Workspace cleanup

- Every workspace created by the harness is marked with `.stelae_smoke_workspace` and
  lives under a directory whose name starts with `stelae-smoke-workspace-<timestamp…>`.
- On startup the harness removes any leftover directories that match the prefix +
  marker in your system temp directory, so re-running the script after `--keep-workspace`
  automatically tears down old sandboxes (unless you also pass `--reuse-workspace --workspace <path>` to protect a specific sandbox).
- To delete a specific kept workspace later, run
  `python scripts/run_e2e_clone_smoke_test.py --cleanup-only --workspace /path/to/workspace`.
  Without `--workspace`, the command purges every detected smoke workspace and exits.

## Codex automation stages

Each automatic run captures three transcripts:

1. **`bundle-tools`** – Captures one `tools/list` snapshot for diagnostics and then
   calls `workspace_fs_read` (`read_file`), `grep`
   (`pattern="manage_stelae"`), and finally `manage_stelae`
   (`list_discovered_servers`). Each call must be attempted in that order; a
   “tool missing” failure still counts as useful telemetry.
2. **`install`** – Calls `manage_stelae` with
   `{"operation":"install_server","params":{"name":"qdrant","target_name":"qdrant_smoke","force":true}}`
   and waits for completion, then issues a read-only verification call.
3. **`remove`** – Calls `manage_stelae` to remove `qdrant_smoke` and verifies the
   catalog is clean.

The JSONL files prove exactly which MCP calls executed and are parsed by
`stelae_lib.smoke_harness.summarize_tool_calls`. If a future change renames tools or
alters the expected sequence, update the harness expectations and the accompanying
unit tests (`tests/test_codex_exec_transcript.py`).

## Manual fallback (optional)

- `--manual` writes the full playbook/result scaffolding (mirroring the original
  flow) and exits immediately so you can run the MCP steps manually via the Codex MCP
  wrapper or another tooling path. Rerun the harness (without `--manual`) once the
  manual steps succeed.
- `--manual-stage bundle-tools|install|remove` converts individual stages into
  resumable checkpoints. The harness stops right before the selected stage, writes
  `manual_stage_<stage>.md` describing the required Codex prompt, and exits. After
  completing the manual stage, rerun with `--workspace <path> --reuse-workspace` and
  omit that `--manual-stage` so automation can continue with the remaining stages.

## Feedback + cleanup

After Codex (auto or manual) finishes, the harness:

1. Runs the remaining pytest modules and `make verify-clean` from inside the clone.
2. Captures any failures with full logs and leaves the workspace intact for triage. A
   clean run deletes the workspace unless `--keep-workspace` is set.
3. Stops the sandbox PM2 daemon so background processes do not linger.

Rerun the script whenever you need to validate that the repo can be cloned, booted,
managed, and tested end-to-end without relying on a long-lived development machine.
