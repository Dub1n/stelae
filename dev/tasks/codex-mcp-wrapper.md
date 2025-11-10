# Task: Codex MCP wrapper

Related requirement: `dev/progress.md` → Action Items → "Add automated/manual smoke coverage for the self-managing MCP clone."

Tags: `#infra`, `#tooling`

## Checklist

- [ ] Research Codex MCP integration points and determine the supported interface for launching sandboxes / missions programmatically.
- [ ] Define the wrapper contract (env variables, workspace selection, mission instructions, completion/failure signaling) so it can be reused by the e2e smoke test and future automation.
- [ ] Implement the wrapper (CLI or service) that spawns Codex MCP instances with the specified env/layout and exposes hooks for orchestrating tool usage.
- [ ] Establish dev vs. released isolation (dedicated repo + virtualenv/sandbox) so experimental builds never overwrite the in-use binary; document how to point Stelae at the published wrapper via bundle/install, and how to expose a separate dev instance (distinct command/env/port) without swapping binaries.
- [ ] Document how to install/configure the wrapper locally (prereqs, env vars, usage examples).
- [ ] Update spec/progress/task entries.
- [ ] Commit with message `infra: add codex mcp wrapper` after tests.

## References

- Code: TBD (likely new `scripts/codex_mcp_wrapper.py` or similar).
- Tests: future integration test once the wrapper can be invoked headlessly, plus manual validation notes.
- Docs: `README.md`, `AGENTS.md`, future wrapper usage guide.

## Notes

- This task unblocks the e2e clone smoke test; without a reliable wrapper we cannot automate the MCP portion. If research shows Codex MCP cannot be driven programmatically, capture the findings and coordinate on alternative approaches (manual-only flow, mock agent, etc.).
- Favor a design where the wrapper can accept missions via JSON/YAML so other automation can reuse it later (e.g., regression suites, onboarding scripts).
- Keep development builds sandboxed (separate virtualenvs/repos, overlays pointing to custom paths and unique ports/pm2 names) so the production wrapper remains untouched until upgrades are intentional, and both published/dev instances can coexist.
- If this task changes dependency relationships, regenerate the task dependency map (`dev/tasks/*_task_dependencies.json`) accordingly.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
