# Task: E2E clone smoke test (Codex MCP harness)

Related requirement: `dev/progress.md` → Action Items → "Add automated/manual smoke coverage for the self-managing MCP clone".

Tags: `#infra`, `#tests`

## Checklist

- [ ] Land a Codex MCP wrapper (or equivalent orchestrator) that can launch sandboxes with caller-provided env/layout and hand structured missions to the agent.
- [ ] Build an automation harness that clones the repo into a temp workspace, points `STELAE_CONFIG_HOME`/`.env` at that sandbox, renders + restarts the stack, and drives the CLI portions of `stelae.manage_stelae` (install/remove) while asserting the git tree stays clean.
- [ ] Write the companion manual playbook so testers can launch the Codex MCP wrapper inside the sandbox, follow the scripted MCP interactions (install server via tool, exercise it, remove it, finish), and feed results back to the harness/orchestrator.
- [ ] If the Codex MCP wrapper cannot be delivered in time, fall back to a documented manual MCP procedure (still using the sandbox + CLI harness) and capture the gap in the task notes.
- [ ] Update README/AGENTS/docs with instructions for running the smoke test (both automated portion and the human-in-the-loop MCP steps).
- [ ] Update spec/progress/task files.
- [ ] Commit with message `infra: add e2e clone smoke test harness` after tests.

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

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
