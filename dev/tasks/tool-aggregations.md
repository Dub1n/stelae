# Task: Introduce Declarative Tool Aggregations

Related requirement: `dev/progress.md` → Tooling Quality → "Let operators declutter manifests by grouping low-level tools under higher-level composite MCP tools."

Tags: `#infra`, `#feature`, `#docs`

## Checklist

- [ ] Define `config/tool_aggregations.json` + JSON Schema capturing aggregations, hidden tools, and operation mappings.
- [ ] Implement a dedicated stdio helper (`scripts/tool_aggregator_server.py`) that loads the config, registers aggregated tools, and dispatches operations to downstream servers via the proxy.
- [ ] Extend restart/render workflow to validate the aggregation config and ensure the helper is launched by default; use a small orchestration script rather than bloating `render_proxy_config`.
- [ ] Wire aggregation "hides" into overrides so original tools stay disabled in manifests when wrapped.
- [ ] Add pytest coverage for config validation + dispatch behavior, plus docs (README, SPEC, ARCHITECTURE) explaining the workflow.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `feature: add tool aggregation helper` after tests.

## References

- Code: `scripts/tool_aggregator_server.py` (new), `scripts/restart_stelae.sh`, `config/tool_overrides.json`
- Tests: new `tests/test_tool_aggregations.py`, existing override/manifest runtime tests
- Docs: `README.md`, `docs/SPEC-v1.md`, `docs/ARCHITECTURE.md`

## Notes

- Aggregations should be purely declarative: adding an entry in the JSON file is enough for the helper to expose a new high-level tool on the next restart.
- The helper must preserve the existing input/output schemas agents see—each aggregated tool publishes a single manifest schema, then rewrites arguments/results per operation before calling the downstream tool.
- Make it easy to hide groups of tools without touching `tool_overrides.json` by letting the helper emit the needed `enabled:false` overrides programmatically.
- Consider future extensions like per-operation permissions or telemetry tagging when shaping the schema.
- Config must include per-operation field mappings + validation hints so the helper can fail fast (if required inputs are missing) and translate aggregated payloads into each downstream tool’s schema without ambiguity.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
