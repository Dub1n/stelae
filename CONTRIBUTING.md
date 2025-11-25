# Contributing

Thanks for your interest in Stelae! We welcome contributions that improve stability, tooling, and docs. Please skim this guide before you start; it points you to the detailed runbooks and flags to avoid common pitfalls.

## Getting started

- Read `DEVELOPMENT.md` for the full stack overview, restart flow, and paths.
- Use the repo virtualenv (`.venv`) for tests and scripts. Quick check: `make test` (runs `.venv/bin/pytest tests` with the right `PYTHONPATH`).
- Keep workspaces on ext4 inside WSL (e.g., `~/dev/...`, `TMPDIR=~/tmp`); the harness aborts on `/mnt/<drive>` paths by default.

## Restart/build flags

- Restarts default to reusing the stamped proxy binary (`--skip-proxy-build`). If the stamp doesn’t match the current proxy commit, the restart fails with guidance to rebuild.
- You can force a rebuild by dropping the skip flag (e.g., remove it from `STELAE_RESTART_ARGS`), or rerun the harness without reuse so the sandbox builds fresh.
- Harness defaults are conservative: `--no-pm2-kill`, `--no-port-kill`, serialized Go builds (`GOFLAGS=-p=1`, `GOMAXPROCS=1`), and `--pytest-scope structural`. Enable heavier paths only when needed.

## Diag logging

- `--capture-diag-logs` starts `dmesg`/`tail -F /var/log/syslog`/`top`/`vmstat` plus `free -h` snapshots and a pm2 log snapshot into `logs/diag/`. These commands may require sudo or be unavailable on some systems. If they can’t start, the harness aborts unless you pass `--force-no-logs`.
- Keep diag logs on ext4 (e.g., the repo’s `logs/diag/`); avoid `/mnt/<drive>`.

## Tests

- Run `make test` before sending changes. This covers unit/integration tests plus harness guardrails.
- Some tests skip when external binaries are missing (e.g., Codex wrapper smoke); that’s expected.

## Style and safety

- Don’t write generated/runtime artifacts into the repo; user overlays live under `${STELAE_CONFIG_HOME}`, runtime under `${STELAE_STATE_HOME}`.
- Avoid adding defaults to `tool_aggregations.json`—bootstrap keeps it empty; starter bundle installs populate it.
- Keep new flags documented in `docs/e2e_clone_smoke_test.md` and `DEVELOPMENT.md`.

## Questions

Open an issue or start a discussion if you’re unsure about flags, environment setup, or WSL quirks. We’d rather help early than debug avoidable restarts or missing diagnostics later.
