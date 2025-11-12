# Task: Stelae tool aggregation visibility & schema dedupe

Related requirement: `dev/progress.md` → Catalog consistency → "Keep the public Stelae MCP catalog limited to the curated aggregates so Codex trusts stay clean."

Tags: `#infra`, `#tooling`

## Checklist

- [x] Baseline today’s `tool_aggregations` overlay + runtime overrides to confirm which raw tools still leak into `tools/list` and capture the exact duplicate-schema output (`doc_fetch_suite`, `workspace_fs_*`, etc.).
- [x] Add a dedupe pass to the aggregation renderer (or override exporter) so `enum`/`required` arrays contain unique entries before they reach the proxy, and ensure hideTool overlays propagate into `${STELAE_CONFIG_HOME}` before runtime files are emitted.
- [x] Extend tests (unit + an integration smoke that inspects a rendered manifest) to assert that only the aggregate tools appear and that their schemas remain valid JSON Schema (no duplicate array members).
- [x] Update docs/progress/task references plus any troubleshooting notes that mention catalog visibility.
- [x] Commit with message `project: stelae aggregation visibility fix` after tests.

## References

- Code: `scripts/process_tool_aggregations.py`, `stelae_lib/integrator/tool_aggregations.py`, `stelae_lib/integrator/tool_overrides.py`, `scripts/restart_stelae.sh`.
- Tests: add/extend coverage next to `tests/test_tool_aggregations.py` (or create if missing) plus a manifest-parsing regression under `tests/test_streamable_mcp.py`.
- Docs: `docs/ARCHITECTURE.md` (catalog handoff section), `docs/e2e_clone_smoke_test.md`, `dev/tasks/stelae-mcp-catalog-consistency.md`.

## Notes

- Current `tools/list` output shows duplicate `enum`/`required` entries for aggregates like `doc_fetch_suite`, causing Codex MCP clients to reject the schema (`Invalid schema for function … has non-unique elements`).
- Overlays must remain authoritative: dedupe logic should run after merging repo template + `${STELAE_CONFIG_HOME}/stelae/config/tool_aggregations.local.json` so local hideTool overrides still apply.
- Once the fix lands, rerun the catalog trials (`logs/codex-catalog-trial-*.jsonl`) to capture a passing baseline for the clone smoke harness.

## Outcome

- Validated the current overlays by diffing `~/.config/stelae/stelae/config/tool_aggregations.local.json` and the runtime manifest, confirming that Docy’s raw tools were still enabled and that `enum`/`required` arrays doubled up whenever overlays re-applied.
- `scripts/process_tool_aggregations.py` now runs in `--scope local` by default so `${STELAE_CONFIG_HOME}` only receives user-defined aggregates before exporting `${TOOL_OVERRIDES_PATH}`, eliminating the race where runtime files were emitted from stale overlays.
- `ToolOverridesStore` canonicalizes merged overrides by deduplicating JSON Schema `enum`/`required` values, so repeated renders or local overlay edits cannot corrupt the manifest.
- Added regression tests: `tests/test_tool_aggregations.py::test_aggregation_runtime_dedupes_and_hides` validates the aggregation pipeline hides raw Docy tools and keeps schemas unique, while `tests/test_streamable_mcp.py::test_rendered_manifest_contains_only_aggregates` inspects a rendered manifest snapshot to ensure only aggregate tools remain enabled.
- Updated the architecture and smoke-test docs to call out the new dedupe behavior plus the requirement to rerun the aggregation renderer whenever catalog visibility drifts.
- Locked the tracked template down to the in-repo suites (currently `manage_docy_sources`) and added `scripts/process_tool_aggregations.py --scope {local,default}` so the default and overlay passes stay isolated. Local runs no longer flood `tool_overrides.local.json` with built-ins, and `tests/test_tool_aggregations.py::test_overlay_only_excludes_defaults` locks in that behavior.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
