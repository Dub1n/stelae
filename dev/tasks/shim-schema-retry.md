# Task: Shim schema-aware retry ladder

Related requirement: `dev/progress.md` → Requirement Group A → "Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides (with guardrails)."

Tags: `#infra`

Prerequisite: `dev/tasks/tool-override-population.md`

## Checklist

- [x] Teach the shim to read each tool's declared `outputSchema` from `config/tool_overrides.json` before executing a tool.
- [x] Implement retry ladder: pass-through → wrap according to declared schema → generic wrapper → bubble error.
- [x] Ensure fallback annotations/logging capture which step produced the final response.
- [x] Update docs (`README.md`, `docs/ARCHITECTURE.md`, relevant task notes) to describe the new order of operations.
- [x] Update `dev/progress.md` / task references.
- [x] Commit with message `infra: add schema-aware shim retry` after tests.

## References

- Code: `scripts/mcp_output_shim.py`, `config/tool_overrides.json`, `config/tool_schema_status.json`
- Tests: `tests/test_scrapling_shim.py`
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `dev/tasks/tool-override-population.md`

## Notes

- Requires populated overrides (see prerequisite task) so the shim has a baseline schema to compare against.
- Consider surfacing telemetry (e.g., logs or status file note) so we can audit how often each step is used.
- Delivered via `scripts/mcp_output_shim.py` (declared-schema wrapper before specialized + generic fallbacks) and documented in README/architecture notes.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] Progress tracker updated
- [ ] Task log updated
- [ ] Checklist completed
