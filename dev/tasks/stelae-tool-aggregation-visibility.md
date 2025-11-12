# Task: Stelae tool aggregation visibility & schema dedupe

Related requirement: `dev/progress.md` → Catalog consistency → "Keep the public Stelae MCP catalog limited to the curated aggregates so Codex trusts stay clean."

Tags: `#infra`, `#tooling`

## Checklist

- [ ] Baseline today’s `tool_aggregations` overlay + runtime overrides to confirm which raw tools still leak into `tools/list` and capture the exact duplicate-schema output (`doc_fetch_suite`, `workspace_fs_*`, etc.).
- [ ] Add a dedupe pass to the aggregation renderer (or override exporter) so `enum`/`required` arrays contain unique entries before they reach the proxy, and ensure hideTool overlays propagate into `${STELAE_CONFIG_HOME}` before runtime files are emitted.
- [ ] Extend tests (unit + an integration smoke that inspects a rendered manifest) to assert that only the aggregate tools appear and that their schemas remain valid JSON Schema (no duplicate array members).
- [ ] Update docs/progress/task references plus any troubleshooting notes that mention catalog visibility.
- [ ] Commit with message `project: stelae aggregation visibility fix` after tests.

## References

- Code: `scripts/process_tool_aggregations.py`, `stelae_lib/integrator/tool_aggregations.py`, `stelae_lib/integrator/tool_overrides.py`, `scripts/restart_stelae.sh`.
- Tests: add/extend coverage next to `tests/test_tool_aggregations.py` (or create if missing) plus a manifest-parsing regression under `tests/test_streamable_mcp.py`.
- Docs: `docs/ARCHITECTURE.md` (catalog handoff section), `docs/e2e_clone_smoke_test.md`, `dev/tasks/stelae-mcp-catalog-consistency.md`.

## Notes

- Current `tools/list` output shows duplicate `enum`/`required` entries for aggregates like `doc_fetch_suite`, causing Codex MCP clients to reject the schema (`Invalid schema for function … has non-unique elements`).
- Overlays must remain authoritative: dedupe logic should run after merging repo template + `${STELAE_CONFIG_HOME}/stelae/config/tool_aggregations.local.json` so local hideTool overrides still apply.
- Once the fix lands, rerun the catalog trials (`logs/codex-catalog-trial-*.jsonl`) to capture a passing baseline for the clone smoke harness.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed

