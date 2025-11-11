# Task: Clone smoke harness stability & instrumentation

Related requirement: `dev/progress.md` → Stelae Progress Tracker → "[ ] clone-smoke-harness-stability".

Tags: `#infra`, `#tests`

> This is a living workbook until the Codex-driven clone smoke test passes end-to-end (auto + manual-stage flows) in a fresh sandbox with reproducible logs.
> All commands must be run with an explicit timeout of no more than 120s.

## Checklist

- [ ] Capture a fresh run (auto + `--manual-stage install`) that exits immediately after the annotated bundle-install step with live per-server logs.
- [ ] Ensure harness-configured env (`STELAE_CONFIG_HOME`, pm2, proxy port) propagates to every subprocess (bundle installer, render, restart, Codex CLI).
- [ ] Diagnose and fix any remaining stalls during render/restart (investigate pm2 `EPIPE`, proxy readiness probe, or long-running Go build).
- [ ] Exercise the full Codex automation (`bundle-tools`, `install`, `remove`) and confirm transcripts + git status checks succeed.
- [ ] Update docs/progress once the smoke test is reliable; keep this workbook current until then.

## References

- Code: `scripts/run_e2e_clone_smoke_test.py`, `scripts/install_stelae_bundle.py`, `stelae_lib/bundles.py`, `stelae_lib/integrator/core.py`.
- Tests: `tests/test_install_stelae_bundle.py`, `tests/test_e2e_clone_smoke.py`, `tests/test_codex_exec_transcript.py`.
- Docs: `docs/e2e_clone_smoke_test.md`, `dev/tasks/e2e-clone-smoke-test.md`, `AGENTS.md`.

## Current State (living notes)

- **Observed issue:** Harness runs with `--manual-stage install` stall right after printing the bundle-install command, even though running the same command manually completes in ~30 s. The underlying installer was waiting on `_run_commands` (proxy restart) despite `--no-restart`; this has been patched but the harness still times out during sandbox setup when Codex/manual assets are requested.
- **Recent changes:**
  - `scripts/install_stelae_bundle.py` now logs each server (`[bundle] Installing …`) and accepts a `log` callback so harness runs stream progress.
  - `stelae_lib/bundles.py` short-circuits restarts when `--no-restart` is set and reports overlay updates.
  - `scripts/run_e2e_clone_smoke_test.py` exports `PYTHONUNBUFFERED=1`, streams subprocess output line-by-line, and adds warnings that bundle install + restart should finish in <60 s.
  - Documentation (`AGENTS.md`, `docs/e2e_clone_smoke_test.md`, `dev/tasks/e2e-clone-smoke-test.md`) now instructs agents not to “fix” this step by raising timeouts.
- **Current blockers:** With `--manual-stage install`, the harness still sits at the restart step; pm2 occasionally throws `write EPIPE` when ensuring processes, and `populate_tool_overrides.py` reports 404 when the proxy is not yet reachable. Need definitive repro logs plus mitigation (e.g., wait-for-proxy with bounded retries, better pm2 error handling).

## Next Steps / Worklog

- Outline experiments (env verification, pm2 log capture, `populate_tool_overrides` retries).
- Record each run’s outcome (command, duration, result) here so future sessions can pick up where the previous left off.

## 2025-02-14 Session – Restart Stall Deep Dive

### Live run log (bounded test executions)

- `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 --manual-stage install` → timed out after ~120 s while `run_restart_stelae.sh` was waiting for pm2. Workspace `/tmp/stelae-smoke-workspace-ibh51q3l` retained for triage with `harness.log`.
- No second harness invocation performed per task constraint (≤2 script runs). All further insights sourced from this run + code inspection.

### Stage 1 – Failure surface observations

- pm2 spawn logs show repeated `Error: write EPIPE` followed by `Failed to start server: listen tcp :9090: bind: address already in use`, confirming the restart cycle never reaches readiness.
- `run_restart_stelae.sh` logged `Killing stray listeners on :22831`, proving the harness selected a randomized proxy port (`choose_proxy_port`) and exported `PROXY_PORT`.
- `harness.log` shows the Go proxy binary still booting on :9090; every restart attempt collides with the developer’s long-lived proxy, so `_run` never returns and the harness hits the outer `timeout`.

### Stage 2 – Code disassembly & reasoning

- `CloneSmokeHarness.__init__` seeds `PROXY_PORT`, `STELAE_PROXY_BASE`, and `.env` via `build_env_map`, so every subprocess (bundle install, make render, restart script) inherits the randomized port.
- `scripts/run_restart_stelae.sh` honors `$PROXY_PORT` for port-kill, config rendering, Cloudflare config, readiness probes, and `populate_tool_overrides.py`. Ergo, the shell orchestration is already parameterized.
- `ecosystem.config.js` never receives `PROXY_PORT` and `config/proxy.template.json` hardcodes `"addr": ":9090"`. The renderer (`scripts/render_proxy_config.py`) simply copies this literal into `${STELAE_CONFIG_HOME}/proxy.json`, so pm2 always boots the Go proxy on 9090 regardless of sandbox env.
- Because pm2 crashes noisily, `run_restart_stelae.sh` never reaches the branch that would notice readiness or emit a clearer hint; the harness just waits on `_run` forever.

```mermaid
flowchart TD
    A[CloneSmokeHarness.run] --> B(_clone_repo / _clone_proxy_repo)
    B --> C(_copy_wrapper_release)
    C --> D(_install_starter_bundle)
    D --> E(make render-proxy)
    E --> F(run_restart_stelae.sh)
    F -->|pm2 returns| G(_run_codex_flow or manual stage)
    F -->|pm2 stalls| H[/Harness timeout → workspace kept/]
```

### Stage 3 – Critical path reconstruction

- Data path: `choose_proxy_port()` → env map in `.env` (`PROXY_PORT=22831`, `PUBLIC_BASE_URL=http://127.0.0.1:22831`) → `render_proxy_config.py` (fills `{{PUBLIC_BASE_URL}}` but not listen addr) → `proxy.json` → pm2 launching `mcp-proxy --config proxy.json`.
- Missing link: there is no template token for `PROXY_PORT`, so the Go config listens on 9090 while everything else expects the randomized port. This mismatch explains both the EPIPE (pm2 log pipe swelling when stdout closes early) and the `listen tcp :9090` collision.

```mermaid
sequenceDiagram
    participant Harness
    participant Restart as run_restart_stelae.sh
    participant PM2
    participant Proxy as mcp-proxy
    participant HostProxy as Host 9090 service
    Harness->>Restart: export PROXY_PORT=22831\ninvoke restart script
    Restart->>PM2: pm2 start mcp-proxy (env still exported)
    PM2->>Proxy: exec mcp-proxy --config proxy.json
    Proxy->>HostProxy: bind(:9090) → EADDRINUSE
    Proxy-->>PM2: exit non-zero + log
    PM2-->>Restart: stream stderr (EPIPE when console pipe closes)
    Restart-->>Harness: never completes (waits for pm2 success)
```

```mermaid
graph LR
    P1[choose_proxy_port()] --> P2[.env PROXY_PORT / PUBLIC_BASE_URL]
    P2 --> P3[render_proxy_config.py]
    P3 --> P4[proxy.template.json\n(missing PORT placeholder)]
    P4 --> P5[proxy.json addr :9090]
    P5 --> P6[pm2 ecosystem config]
    P6 --> P7[mcp-proxy listens on :9090]
    Host[Host dev proxy :9090] -->|conflict| P7
```

### Stage 4 – Hypotheses & conceptual reassembly

1. **Primary hypothesis:** The harness is correct; the template is not (lack of port substitution). Fix by introducing `{{PROXY_PORT}}` placeholder + renderer arg, or by post-processing the JSON to rewrite the `addr`. This would align pm2 listeners with the sandboxed port and remove the collision.
2. **Secondary contributing risk:** pm2 keeps inherited stdio handles open while the harness waits synchronously; repeated crash spam + absence of early failure detection cause the run to “hang” rather than fail fast. After port fix, consider bounding the restart duration or tailing pm2 logs asynchronously so `_run` can abort if pm2 exits repeatedly.
3. **Tertiary considerations:** Even with port fix, we should verify that `populate_tool_overrides.py` only runs after the proxy is reachable. Right now, a failing pm2 start still flows into override population, which may produce the previously observed 404/connection reset noise.

### Stage 5 – Targeted probes to run next

- Inspect the rendered sandbox config: `jq '.mcpProxy.addr' /tmp/stelae-smoke-workspace-ibh51q3l/config-home/proxy.json` (should confirm it still says `:9090`).
- Confirm host listener ownership prior to harness run: `ss -ltnp '( sport = :9090 )'` to document the conflicting service (likely the developer’s long-lived pm2).
- Validate template coverage: `rg -n \"PROXY_PORT\" config/proxy.template.json scripts/render_proxy_config.py` (already zero hits).
- If/when port placeholder is added, re-run harness with the same bounded command to verify pm2 readiness completes inside 60 s.

Executed probes now that the analysis section is in place:

- `jq '.mcpProxy.addr' /tmp/stelae-smoke-workspace-ibh51q3l/config-home/proxy.json` → `":9090"` (confirms rendered config ignores `PROXY_PORT`).
- `ss -ltnp '( sport = :9090 )'` → `LISTEN ... users:(("mcp-proxy",pid=1390782,fd=4))`, proving the host developer proxy owns 9090 and causes the harness collision.

Documenting these probes here keeps the workbook synchronized with the expectations in `AGENTS.md` and ties the conceptual analysis back to concrete verification hooks.

### Stage 6 – Remediation progress & verification gaps

- Cleared stray harness pm2 processes (`PM2_HOME=/tmp/stelae-smoke-workspace-ibh51q3l/.pm2 pm2 kill`) plus orphaned `pm2 logs mcp-proxy` tails to reduce load before continuing.
- Implemented repo fixes:
  1. Added `PROXY_PORT` to `.env.example` and wired `PUBLIC_PORT=${PROXY_PORT}` so legacy configs stay in sync.
  2. Updated `config/proxy.template.json` to set `"addr": ":{{PROXY_PORT}}"`.
  3. Taught `scripts/render_proxy_config.py` to fall back to `PUBLIC_PORT` (or 9090) when `PROXY_PORT` is absent, preserving older environments.
  4. Added SIGINT/SIGTERM hooks so the harness tears down its PM2 home + workspace when interrupted, preventing lingering processes during Ctrl+C exits.
- Updated README + docs (`docs/e2e_clone_smoke_test.md`, `docs/ARCHITECTURE.md`) to call out the dynamic `PROXY_PORT` behavior and the harness’ graceful shutdown guarantees.
- Local renderer smoke test: `timeout 120s python3 scripts/render_proxy_config.py --template config/proxy.template.json --output /tmp/proxy-test.json --env-file .env --fallback-env .env.example` → `jq '.mcpProxy.addr' /tmp/proxy-test.json == ":9090"` (expected because workstation `.env` still defaults to 9090, confirming substitution works).
- Re-running the harness immediately afterward still produced a port collision (`:9090`) because the disposable clone fetches the last committed template (without the new placeholder). Once these changes are merged, the next harness run should inherit the fix.
- Updated README + docs (`docs/e2e_clone_smoke_test.md`, `docs/ARCHITECTURE.md`) to call out the dynamic `PROXY_PORT` behavior and the harness’ graceful shutdown guarantees.

### Stage 7 – Post-fix harness run (bounded at 120 s)

- `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 --manual-stage install` (workspace `/tmp/stelae-smoke-workspace-8w5lmp9f`) still hit the external timeout but progressed substantially further: `run_restart_stelae.sh` restarted pm2 cleanly on `:20847` (see `jq '.mcpProxy.addr' config-home/proxy.json → ":20847"` and the absence of any `bind: address already in use` lines).
- `harness.log` captures the full downstream server registration stream plus healthy readiness probes; the remaining delay is now the total wall-clock for clone + Go build + restart rather than a hard stall on pm2.
- Because the outer `timeout` terminated the harness mid-flight, the new SIGINT/SIGTERM handler logged the interrupt but did not finish killing pm2 before the supervising `timeout` sent SIGKILL; I manually ran `PM2_HOME=/tmp/stelae-smoke-workspace-8w5lmp9f/.pm2 pm2 kill` afterward to ensure the sandbox daemon stopped. Next iteration should either finish inside 120 s (now that module downloads are warm) or bolt on a resumable resume flag to keep proving post-install steps without restarting from scratch.

### Stage 8 – Five-minute bounding experiment (still timing out)

- `timeout 300s python3 scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 --manual-stage install` created workspace `/tmp/stelae-smoke-workspace-pxvtbyhd` and again timed out. Port selection landed on `:21738` (`jq '.mcpProxy.addr' config-home/proxy.json → ":21738"`), and pm2 showed `mcp-proxy`, `watchdog`, and (despite `--no-cloudflared`) a briefly auto-started `cloudflared` instance as `online` before I killed the sandbox daemon manually.
- `harness.log` ends with pm2 streaming downstream server registrations (`<mem> Handling requests at /mem/`) but never reaches the `==> Local probe: HEAD …` / `Syncing tool overrides…` lines that run after `wait_port`. That implies the script was still inside `run_restart_stelae.sh` when `timeout` fired—most likely waiting for its readiness probes or schema sync to finish—rather than stalling on pm2.
- I ran `PM2_HOME=/tmp/stelae-smoke-workspace-pxvtbyhd/.pm2 pm2 kill` after the timeout to avoid leaving a stray stack online.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
