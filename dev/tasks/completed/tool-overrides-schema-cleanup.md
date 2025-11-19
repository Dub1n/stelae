# Task: Normalize Tool Overrides Schema & Automation

Related requirement: `dev/progress.md` → Tooling Quality → "Ensure tool overrides are canonical, validated, and per-server to prevent drift."

Tags: `#infra`, `#docs`

## Checklist

- [x] Audit current overrides producers/consumers (Python integrator, populate script, Go proxy) and map duplication cases.
- [x] Define + land schema v2 (JSON Schema + migration helpers) and add validator hooks to writers.
- [x] Update overrides producers (ToolOverridesStore, populate script, proxy list output) to emit per-server entries only; add migration from legacy layout.
- [x] Extend Go proxy + pytest to enforce new structure and server metadata in tools/list.
- [x] Update README/ARCHITECTURE to document the schema and validation flow.
- [x] Update spec/progress/task file.
- [ ] Commit with message `infra: normalize tool override schema` after tests.

## References

- Code: `stelae_lib/integrator/tool_overrides.py`, `scripts/populate_tool_overrides.py`, `~/apps/mcp-proxy/tool_overrides.go`
- Tests: `tests/test_populate_tool_overrides.py`, `tests/test_tool_overrides_runtime.py`, Go proxy unit tests
- Docs: `README.md`, `docs/ARCHITECTURE.md`

## Notes

- Populators now rely on the proxy’s `x-stelae` metadata; make sure rebuilt binaries are deployed (`~/apps/mcp-proxy/build/mcp-proxy`) before running the restart script on other hosts.
- Manual runs of `scripts/populate_tool_overrides.py` should export `PYTHONPATH=$STELAE_DIR` so the helper can import the shared store implementation.
- If additional dependencies between tasks change, regenerate dependency maps per `dev/tasks/*_task_dependencies.json`.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
