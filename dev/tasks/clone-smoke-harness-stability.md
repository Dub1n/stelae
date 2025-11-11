# Task: Clone smoke harness stability & instrumentation

Related requirement: `dev/progress.md` → Stelae Progress Tracker → "[ ] clone-smoke-harness-stability".

Tags: `#infra`, `#tests`

> This is a living workbook until the Codex-driven clone smoke test passes end-to-end (auto + manual-stage flows) in a fresh sandbox with reproducible logs.

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

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
