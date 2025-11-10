# Task: Stabilize overlays + local runtime parity

Related requirement: `docs/current/progress.md` → Configuration Hygiene → "Keep shipped defaults generic; let per-instance customisation live outside the repo while remaining auto-loaded."

Tags: `#infra`

## Checklist

- [ ] Fix failing overlay regressions (`tests/test_repo_sanitized.py::test_tracked_configs_remain_placeholder_only` and `tests/test_stelae_integrator.py::test_discover_servers_hydrates_qdrant`).
- [ ] Ensure full stack can run locally without Cloudflare (CF setup only required for remote exposure) and add a regression test that exercises the local-only path.
- [ ] Audit config/render scripts to confirm every tracked file stays generic; document any gaps and, if feasible, add/extend a repo hygiene test that fails when local paths creep into tracked templates.
- [ ] Update docs/spec/progress/task entries with the new expectations/tests.
- [ ] Commit with message `infra: stabilize local overlay runtime` after tests.

## References

- Code: `scripts/render_proxy_config.py`, `scripts/render_cloudflared_config.py`, `scripts/restart_stelae.sh`, `stelae_lib/integrator/*`, `tests/test_repo_sanitized.py`, `tests/test_stelae_integrator.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_stelae_integrator.py`, (new local-only runtime test TBD).
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`.

## Notes

- The new overlay plumbing broke two tests; fix them first to re-establish a green baseline.
- For the local-only workflow, codify expectations (e.g., skip Cloudflare unless explicitly requested) and assert via tests that runtimes work without external tunnels.
- Repo hygiene test currently scans a couple files; expand coverage if practical (fail fast when absolute paths sneak into tracked templates). If such a check is infeasible, document why in the implementation notes.
- If this task changes dependency graphs, regenerate the relevant JSON under `dev/tasks/*_task_dependencies.json` and attach the update when filing progress.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
