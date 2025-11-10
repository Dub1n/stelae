# Task: Repo maintenance & architecture refresh

Related requirement: `docs/current/progress.md` → Project Hygiene → "Keep documentation, automation, and code patterns synchronized so contributors can trust the repo state."

Tags: `#infra`

## Checklist

- [ ] Review `docs/ARCHITECTURE.md`, README sections, and diagrams to ensure they reflect the current overlay/local-runtime model; update or prune stale content.
- [ ] Consolidate duplicated env/config loading patterns (renderers, helper scripts) around `stelae_lib.config_overlays` utilities where practical.
- [ ] Add a repo hygiene helper (e.g., `make verify-clean`) or documented workflow that checks for unintended modifications to tracked files after running common automation.
- [ ] Update spec/progress/task files with any changes or guardrails introduced.
- [ ] Commit with message `infra: refresh repo maintenance` after tests.

## References

- Code: `scripts/*.py`, `Makefile`, `stelae_lib/config_overlays.py`.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`.
- Tests: existing hygiene tests (`tests/test_repo_sanitized.py`, future verify-clean harness) as needed.

## Notes

- Focus on consistency and clarity: remove obsolete instructions, ensure environment/setup sections across docs agree, and highlight the overlay model wherever contributors touch configs.
- When consolidating helpers, prefer small shared functions/modules over copy/paste in individual scripts.
- The optional `verify-clean` helper can be a simple script that runs the usual renderers/restart sequences and asserts `git status --porcelain` remains empty, even if it’s just documentation initially.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
