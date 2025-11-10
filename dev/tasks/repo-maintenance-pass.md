# Task: Repo maintenance & architecture refresh

Related requirement: `docs/current/progress.md` → Project Hygiene → "Keep documentation, automation, and code patterns synchronized so contributors can trust the repo state."

Tags: `#infra`

## Checklist

- [x] Review `docs/ARCHITECTURE.md`, README sections, and diagrams to ensure they reflect the current overlay/local-runtime model; update or prune stale content.
- [x] Consolidate duplicated env/config loading patterns (renderers, helper scripts) around `stelae_lib.config_overlays` utilities where practical.
- [x] Add a repo hygiene helper (e.g., `make verify-clean`) or documented workflow that checks for unintended modifications to tracked files after running common automation.
- [x] Update spec/progress/task files with any changes or guardrails introduced.
- [x] Commit with message `infra: refresh repo maintenance` after tests.

## References

- Code: `scripts/*.py`, `Makefile`, `stelae_lib/config_overlays.py`.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`.
- Tests: existing hygiene tests (`tests/test_repo_sanitized.py`, future verify-clean harness) as needed.

## Notes

- Focus on consistency and clarity: remove obsolete instructions, ensure environment/setup sections across docs agree, and highlight the overlay model wherever contributors touch configs.
- When consolidating helpers, prefer small shared functions/modules over copy/paste in individual scripts.
- The optional `verify-clean` helper can be a simple script that runs the usual renderers/restart sequences and asserts `git status --porcelain` remains empty, even if it’s just documentation initially.

### Current observations (2025-11-10)

- **Docs drift hotspots:** README’s “Docy Source Catalog” and “Declarative Tool Aggregations” sections still assume every downstream server ships by default, while the architecture doc now emphasizes the local-only restart path. Use this pass to align wording so the “core vs optional” stack boundaries are explicit across README/ARCHITECTURE/AGENTS.
- **Env parsing duplication:** Both `scripts/render_proxy_config.py` and `scripts/render_cloudflared_config.py` reimplement `parse_env_file`/variable expansion. Consider moving that logic into `stelae_lib.config_overlays` (or a shared helper) and importing it in the renderers so future tweaks to overlay resolution happen in one place.
- **Renderer outputs vs git hygiene:** `tests/test_repo_sanitized.py` currently guards `.env.example`, `config/tool_overrides.json`, `config/tool_aggregations.json`, and `config/proxy.template.json`, but `make render-proxy` still writes `config/proxy.json` inside the repo when `PROXY_CONFIG` isn’t overridden. A `make verify-clean` target could run `make render-proxy`, `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`, and ensure `git status --porcelain` stays empty to catch regressions automatically.
- **Task references:** `dev/tasks/local-runtime-hardening.md` already documents the hygiene test additions; fold any new guardrails into that file (and `dev/progress.md`) so future contributors can see why the checks exist.

## Implementation Notes (2025-11-10)

- Added `parse_env_file`, `expand_env_values`, and `load_layered_env` helpers to `stelae_lib.config_overlays`, then refactored the proxy/cloudflared renderers plus the integrator to consume them. This keeps env layering/expansion behavior consistent everywhere and gives us direct test coverage via `tests/test_config_overlays.py`.
- Introduced `scripts/verify_clean_repo.sh` and the accompanying `make verify-clean` target. The helper snapshots `git status`, runs `make render-proxy` and the default local-only restart flags, and fails loudly if tracked files change. It also exposes `--skip-restart` and `VERIFY_CLEAN_RESTART_ARGS` knobs for lighter dev setups.
- Updated README, `docs/ARCHITECTURE.md`, and `AGENTS.md` to call out the core-vs-optional stack boundary, reiterate the local-only restart flow, and document the new hygiene helper so contributors know how to keep overlays outside the repo.
- Synced `dev/tasks/local-runtime-hardening.md`, this task file, and `dev/progress.md` with the new guardrail so the project history explains why `make verify-clean` exists.

## Verification

- `pytest tests/test_config_overlays.py tests/test_repo_sanitized.py`
- `./scripts/verify_clean_repo.sh --skip-restart`

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] progress.md updated
- [x] Task log updated
- [x] Checklist completed
