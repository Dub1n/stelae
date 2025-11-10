# Task: E2E clone smoke test (Codex MCP harness)

Related requirement: `dev/progress.md` → Action Items → "Add automated/manual smoke coverage for the self-managing MCP clone".

Tags: `#infra`, `#tests`

## Checklist

- [x] Land a Codex MCP wrapper (or equivalent orchestrator) that can launch sandboxes with caller-provided env/layout and hand structured missions to the agent. _(Delivered separately in `~/dev/codex-mcp-wrapper`; this task consumes the released bundle.)_
- [x] Build an automation harness that clones the repo into a temp workspace, points `STELAE_CONFIG_HOME`/`.env` at that sandbox, renders + restarts the stack, and drives the CLI portions of `stelae.manage_stelae` (install/remove) while asserting the git tree stays clean.
- [x] Write the companion manual playbook so testers can launch the Codex MCP wrapper inside the sandbox, follow the scripted MCP interactions (install server via tool, exercise it, remove it, finish), and feed results back to the harness/orchestrator.
- [x] If the Codex MCP wrapper cannot be delivered in time, fall back to a documented manual MCP procedure (still using the sandbox + CLI harness) and capture the gap in the task notes. _(N/A – wrapper available; playbook references the release copy.)_
- [x] Update README/AGENTS/docs with instructions for running the smoke test (both automated portion and the human-in-the-loop MCP steps).
- [x] Update spec/progress/task files.
- [x] Commit with message `infra: add e2e clone smoke test harness` after tests.

## References

- Code: `scripts/install_stelae_bundle.py`, `scripts/stelae_integrator_server.py`, `scripts/run_restart_stelae.sh`, planned Codex MCP wrapper (TBD), future `tests/e2e_clone_smoke.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_install_stelae_bundle.py` (reference for sandbox env handling), new e2e smoke test module.
- Docs: `README.md` (core vs optional flow), `AGENTS.md`, `docs/ARCHITECTURE.md`, new smoke-test instructions page.

## Notes

- The MCP interactions must go through the actual agent transport (JSON-RPC via proxy) to validate manifests, overrides, and tool UX—CLI helpers are only for the automated portion.
- The harness should isolate state by exporting `STELAE_CONFIG_HOME=$(mktemp -d)` (or equivalent) so the smoke test never touches a real workstation’s overlays. Remember to clean up temp dirs even on failure.
- Consider staging the workflow (e.g., `setup`, `manual`, `verify`) so the manual portion slots naturally between automated steps.
- Allocate alternate ports and/or pm2 app names for the smoke-test stack so it never collides with a developer’s running instance, even if both happen to be online simultaneously.
- If this task changes prerequisites or dependency relationships, regenerate the project’s dependency map JSON (see `dev/tasks/*_task_dependencies.json`) and attach the updated file in the related progress planner.

## Outcome

- Added `scripts/run_e2e_clone_smoke_test.py`, which clones Stelae + `mcp-proxy` into a disposable workspace, writes a sandboxed `.env`/`${STELAE_CONFIG_HOME}`, copies an optional Codex wrapper release, runs `make render-proxy` + `scripts/run_restart_stelae.sh`, and exercises `manage_stelae` (install/remove) via the integrator CLI. The harness writes `manual_playbook.md` and `manual_result.json`, then waits for the human-in-the-loop Codex phase before validating/cleaning up.
- Added helper utilities (`stelae_lib/smoke_harness.py`) and a Codex mission stub (`dev/tasks/missions/e2e_clone_smoke.json`) for the manual runbook.
- Documented the workflow in `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and the dedicated guide `docs/e2e_clone_smoke_test.md`.
- Added unit coverage for the helper functions (see `tests/test_e2e_clone_smoke.py`).

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] progress.md updated
- [x] Task log updated
- [x] Checklist completed
