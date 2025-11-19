# Task: Migrate `.env` Workflow to `${STELAE_CONFIG_HOME}`

Related requirement: `dev/progress.md` → Action Items → "Keep workstation-specific configs under `${STELAE_CONFIG_HOME}`".

Tags: `#infra`

## Checklist

- [x] Create a bootstrap helper (`scripts/setup_env.py`) that copies `.env.example` → `${STELAE_CONFIG_HOME}/.env` on first run and maintains a repo-root symlink for backwards compatibility.
- [x] Teach `scripts/restart_stelae.sh` (and any other entry-point scripts) to `set -a; source "${STELAE_CONFIG_HOME}/.env"` before doing any work, falling back to the repo `.env` only if the config-home copy is missing.
- [x] Define `STELAE_ENV_FILE` inside `.env.example` and update all scripts/targets (renderers, Makefile, helper scripts) to reference `$STELAE_ENV_FILE` instead of hardcoding `./.env`.
- [x] Update documentation (`README.md`, `docs/ARCHITECTURE.md`, task logs) to describe the new env location and the bootstrap flow.
- [x] Update spec/progress/task file.
- [ ] Commit with message `infra: move env handling to config home` after tests.

## References

- Code: `scripts/restart_stelae.sh`, `scripts/run_restart_stelae.sh`, `scripts/render_proxy_config.py`, `Makefile` targets that currently source `./.env`.
- Tests: `tests/test_repo_sanitized.py` (verifies templates don’t leak absolute paths); add coverage ensuring the bootstrap script writes to `${STELAE_CONFIG_HOME}`.
- Docs: `README.md` (Environment setup), `docs/ARCHITECTURE.md` (config overlays), `dev/tasks/stelae-smoke-readiness.md`.

## Notes

- `restart_stelae.sh` now sources `${STELAE_ENV_FILE}` (falling back to the repo symlink) before establishing paths so every downstream PM2 process inherits config-home overrides automatically.
- Bootstrap helper is clone-safe: `scripts/setup_env.py` copies `.env.example` into `${STELAE_ENV_FILE}` if missing, migrates existing repo `.env` files into the config home, and falls back to copying when symlinks fail.
- Renderers (`scripts/render_proxy_config.py`, `scripts/render_cloudflared_config.py`), the Makefile, restart helpers, and harness tooling now reference `$STELAE_ENV_FILE` so there’s a single authoritative env path.
- Automation (`scripts/run_e2e_clone_smoke_test.py`, README onboarding, task docs) instructs contributors to run the bootstrap script instead of copying `.env` by hand; the harness writes `${STELAE_CONFIG_HOME}/.env` directly and lets the script maintain `repo/.env`.
- Remember to regenerate any task dependency JSON if the new script becomes a prerequisite for other tasks.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
