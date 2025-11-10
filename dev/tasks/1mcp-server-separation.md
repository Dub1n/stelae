# Task: 1mcp-server fork separation & optional AI plan

Related requirement: `dev/progress.md` → core-stack-modularization → "Ship a minimal core stack plus an optional starter bundle so clones stay lightweight while power users can opt into the full tool suite."

Tags: `#infra`

## Checklist

- [ ] Audit `Dub1n/stelae-1mcpserver` versus upstream 1mcp-server for separation-of-concerns, dependency boundaries, and repo hygiene (docs/scripts/tests/schemas).
- [ ] Determine whether our fork can stay a single repo with optional AI/API integrations (no required keys/dependencies for offline use); if not, document the "slim" vs "slimmable" fork approach and implications.
- [ ] Capture required cleanups (directory layout, scripts, CI/tests) plus the changes needed for an upstream PR that adds opt-in AI features without regressing existing behavior.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: short summary` after tests.

## References

- Code: https://github.com/Dub1n/stelae-1mcpserver , `~/apps/mcp-proxy`, `stelae` repo modules integrating 1mcp discovery/runtime
- Tests: `pytest` suite under `stelae` + any forked 1mcp-server tests we need to align
- Docs: `docs/MCP-servers-list.md`, `ARCHITECTURE.md`, repo-level READMEs for both repos, `docs/templates/task-log.md`

## Notes

- Goal: ensure the fork can submit an upstream PR that merely makes AI integrations optional; no regressions for existing users and no forced API key/dependency installation for offline clones.
- If the fork is already a stripped-down variant that cannot express optional AI toggles cleanly, scope this task to documenting separation-of-concerns gaps plus the work needed for a future "slimmable" fork (keeps current fork slim, outlines new fork that keeps optional AI path) while preferring a single fork where feasible.
- Identify ownership boundaries between `stelae` automation (discovery, overrides, renderers) and the 1mcp-server fork so repos remain clean and changes flow upstream easily.
- Record follow-up items such as dependency pruning, config templating updates, or automation required to keep both repos in sync.
- If this task changes prerequisites or dependency relationships, regenerate the project’s dependency map JSON (see `dev/tasks/*_task_dependencies.json`) and attach the updated file in the related progress planner.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
