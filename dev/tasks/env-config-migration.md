# Task: Migrate `.env` Workflow to `${STELAE_CONFIG_HOME}`

Related requirement: `dev/progress.md` → Action Items → "Keep workstation-specific configs under `${STELAE_CONFIG_HOME}`".

Tags: `#infra`

## Checklist

- [ ] Create a bootstrap helper (e.g. `scripts/setup_env.py`) that copies `.env.example` → `${STELAE_CONFIG_HOME}/.env` on first run and maintains a repo-root symlink for backwards compatibility.
- [ ] Teach `scripts/restart_stelae.sh` (and any other entry-point scripts) to `set -a; source "${STELAE_CONFIG_HOME}/.env"` before doing any work, falling back to the repo `.env` only if the config-home copy is missing.
- [ ] Define `STELAE_ENV_FILE` inside `.env.example`/.env and update all scripts/targets (renderers, Makefile, helper scripts) to reference `$STELAE_ENV_FILE` instead of hardcoding `./.env`.
- [ ] Update documentation (`README.md`, `docs/ARCHITECTURE.md`, task logs) to describe the new env location and the bootstrap flow.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `infra: move env handling to config home` after tests.

## References

- Code: `scripts/restart_stelae.sh`, `scripts/run_restart_stelae.sh`, `scripts/render_proxy_config.py`, `Makefile` targets that currently source `./.env`.
- Tests: `tests/test_repo_sanitized.py` (verifies templates don’t leak absolute paths); add coverage ensuring the bootstrap script writes to `${STELAE_CONFIG_HOME}`.
- Docs: `README.md` (Environment setup), `docs/ARCHITECTURE.md` (config overlays), `dev/tasks/stelae-smoke-readiness.md`.

## Notes

- `restart_stelae.sh` currently shells `grep` against `./.env` and never exports new variables, which breaks Docy and other servers that rely on config-home overrides. Sourcing the config-home copy with `set -a` emits every var to the environment before pm2 starts child processes.
- Bootstrap helper must be clone-safe: if `${STELAE_CONFIG_HOME}/.env` is absent, copy `.env.example`, then (optionally) create `repo/.env` → `${STELAE_CONFIG_HOME}/.env` symlink so IDEs and ad-hoc tooling keep finding it. On Windows/WSL, fall back to copying instead of symlinking when `ln -s` fails.
- Ensure `scripts/render_proxy_config.py`, `scripts/tool_aggregator_server.py`, and any other utilities that currently ingest `./.env` switch to `$STELAE_ENV_FILE` (defaulting to `${STELAE_CONFIG_HOME}/.env`) so there’s a single authoritative path.
- Verify that automation (make targets, pm2 lifecycle helpers, smoke harness) does not source `.env` manually anymore once the script handles it; update docs to instruct contributors to run the bootstrap script instead of copying `.env` by hand.
- Remember to regenerate any task dependency JSON if the new script becomes a prerequisite for other tasks.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
