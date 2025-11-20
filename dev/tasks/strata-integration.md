# Task: Strata capability routing & reconciler promotion

Related requirement: `dev/progress.md` → strata-integration → "Integrate Strata as a first-class capability router so rare tool requests can be promoted via `make promote … TARGET=strata` / `manage_stelae run_reconciler` without bloating the core manifest."

Tags: `#feature` `#infra` `#docs`

## Checklist

- [ ] Implement the reconciler skeleton (`reconciler/reconcile.py`) with `--capability` + `--target core|strata`, consuming 1mcp discovery and emitting proxy/bundle updates per TODO Phase 6.
- [ ] Wire `make promote` (and the MCP `run_reconciler` operation) to invoke the reconciler with capability + target, ensuring Strata promotions skip proxy restarts when possible and core promotions trigger restart automation.
- [ ] Extend Strata tooling (`strata_ops_suite`, bundle metadata, config overlays) so promoted servers can be registered as Strata actions, including auth handling and documentation hooks.
- [ ] Add regression tests (unit + integration) covering reconciler CLI behavior, `manage_stelae` invocation paths, and `strata_ops_suite` operations (discover/execute/auth failure) with promoted servers.
- [ ] Document the workflow in README (Roadmap/Usage), DEVELOPMENT (runbooks), AGENTS (operator expectations), and TODO/progress trackers; include payload examples for `make promote`/`run_reconciler`.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: add strata reconciler support` after tests.

## References

- Code: planned `reconciler/reconcile.py`, `scripts/stelae_integrator_server.py` (`manage_stelae`), bundled `strata_ops_suite` definitions in `bundles/starter/catalog.json`.
- Tests: to extend `tests/test_stelae_integrator.py`, `tests/test_tool_aggregations.py`, smoke harness cases in `dev/tasks/stelae-smoke-readiness.md`.
- Docs: README Roadmap section, TODO.md (Phase 6–7 “Reconciler” & “Strata path”), DEVELOPMENT.md (discovery + Strata references), `dev/tasks/completed/codex-manage-stelae-smoke.md`.

## Notes

- Capability promotions should prefer Strata to avoid inflating the proxy manifest; only promote to `core` when an MCP needs to be globally visible.
- The reconciler must be idempotent, keep `proxy.json` updates atomic, and respect config-home/state-home path guards; CLI + MCP flows share the same implementation.
- Tests/harness should validate both stdio and HTTP consumers (Codex CLI, ChatGPT) can call `strata_ops_suite` to reach newly promoted tools without a restart.
- Align with the portable bundle effort so promoted Strata servers can be packaged as bundles later.
- If this introduces new cross-task dependencies, regenerate the dependency map JSON under `dev/tasks/logs/`.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
