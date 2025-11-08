# Task: Tool override auto-population

Related requirement: `dev/progress.md` → Requirement Group A → "Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides (with guardrails)."

Tags: `#infra`

## Checklist

- [x] Add launcher hook that inspects freshly-connected MCP servers and records their declared `inputSchema`/`outputSchema` into `config/tool_overrides.json` without clobbering manual edits.
- [x] Ensure generated overrides are deterministic and idempotent (skip rewrites when values already match).
- [x] Update `dev/tasks/mcp-auto-loading.md` + `README.md` to explain when/where the auto-population runs.
- [x] Update spec/progress/task file.
- [ ] Commit with message `infra: seed tool overrides` after tests.
- [ ] After completing all steps, rerun `date --iso-8601=seconds`, record the end timestamp, compare against the start time noted below (15-minute threshold decides whether to proceed with `dev/tasks/shim-schema-retry.md`).

## References

- Code: `scripts/mcp_output_shim.py`, `config/tool_overrides.json`, `scripts/render_proxy_config.py`
- Tests: `tests/test_scrapling_shim.py` (extend/clone once new helper lands)
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `dev/tasks/mcp-auto-loading.md`

## Notes

- Delivered via `scripts/populate_tool_overrides.py`, which now supports two modes:
  - `--proxy-url <endpoint>` reuses an existing MCP proxy `tools/list` response (used automatically by `scripts/restart_stelae.sh` after the readiness probe) so we avoid re-spawning downstream servers during ordinary restarts.
  - `--servers <name>` continues to launch specific stdio servers for ad-hoc seeding during development.
- The generator should run during startup (e.g., invoked by `scripts/render_proxy_config.py` or a dedicated `make populate-overrides` step). It must be safe to run repeatedly and only fill missing fields (never erase manual tweaks).
- Coordinate with the shim automation so newly populated schemas feed directly into the retry ladder (pass-through → declared schema → generic shim).
- After this lands, revisit `dev/tasks/mcp-auto-loading.md` to confirm the discovery flow uses the same helper.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] Progress tracker updated
- [ ] Task log updated
- [ ] Checklist completed

## Timestamp Log

- Start: `2025-11-07T12:53:21+00:00`
- End: `2025-11-07T12:57:11+00:00`
- Duration: ~4 minutes (< 15 minutes) → proceed to `dev/tasks/shim-schema-retry.md`.
