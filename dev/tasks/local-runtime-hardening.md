# Task: Stabilize overlays + local runtime parity

Related requirement: `docs/current/progress.md` → Configuration Hygiene → "Keep shipped defaults generic; let per-instance customisation live outside the repo while remaining auto-loaded."

Tags: `#infra`

## Checklist

- [x] Fix failing overlay regressions (`tests/test_repo_sanitized.py::test_tracked_configs_remain_placeholder_only` and `tests/test_stelae_integrator.py::test_discover_servers_hydrates_qdrant`).
- [x] Ensure full stack can run locally without Cloudflare (CF setup only required for remote exposure) and add a regression test that exercises the local-only path.
- [x] Audit config/render scripts to confirm every tracked file stays generic; document any gaps and, if feasible, add/extend a repo hygiene test that fails when local paths creep into tracked templates and verifies routine stack usage leaves `git status` clean.
- [x] Update docs/spec/progress/task entries with the new expectations/tests.
- [x] Commit with message `infra: stabilize local overlay runtime` after tests.

## References

- Code: `scripts/render_proxy_config.py`, `scripts/render_cloudflared_config.py`, `scripts/restart_stelae.sh`, `stelae_lib/integrator/*`, `tests/test_repo_sanitized.py`, `tests/test_stelae_integrator.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_stelae_integrator.py`, (new local-only runtime test TBD).
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`.

## Notes

- The new overlay plumbing broke two tests; fix them first to re-establish a green baseline.
- For the local-only workflow, codify expectations (e.g., skip Cloudflare unless explicitly requested) and assert via tests that runtimes work without external tunnels.
- Repo hygiene test currently scans a couple files; expand coverage if practical (fail fast when absolute paths sneak into tracked templates). If such a check is infeasible, document why in the implementation notes.
- If this task changes dependency graphs, regenerate the relevant JSON under `dev/tasks/*_task_dependencies.json` and attach the update when filing progress.

## Implementation Notes

- Sanitized the tracked override templates so they no longer reference `/home/...`, then expanded the hygiene pytest to cover both `config/tool_overrides.json` and `config/tool_aggregations.json` plus `.env.example` guards. `tests/test_repo_sanitized.py` now enforces that tracked configs stay placeholder-only and that runtime artifacts remain pointed at `${STELAE_CONFIG_HOME}`.
- Updated the integrator’s env layering: user-provided `env_files` are honored (and the last entry becomes the write target) while hydrated defaults fall back to `${STELAE_CONFIG_HOME}/.env.local`. This fixed `tests/test_stelae_integrator.py::test_discover_servers_hydrates_qdrant`.
- Swapped the default restart flags from `--full` to `--keep-pm2 --no-bridge --no-cloudflared`, added `test_restart_defaults_skip_cloudflared`, and documented the new override knob (`STELAE_RESTART_ARGS`) across README + architecture notes so local-only restarts are officially supported.
- Instrumented docs with the new hygiene test guidance, clarified that Cloudflare work is opt-in, and copied the results into this task log + `dev/progress.md`.

## Verification

- `. .venv/bin/activate && PYTHONPATH=$PWD pytest tests/test_repo_sanitized.py tests/test_stelae_integrator.py`
- Manual doc review (README.md, docs/ARCHITECTURE.md) for the updated instructions.

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] progress.md updated
- [x] Task log updated
- [x] Checklist completed
