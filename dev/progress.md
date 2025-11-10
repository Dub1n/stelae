---
doc-type: progress
name: stelae Progress Tracker
tags: [project, progress]
status: draft
last_updated: 08-11-2025
---

# Stelae Progress Tracker

Legend: `[x]` done · `[~]` in progress · `[ ]` not started · `[!]` broken · `[?]` verify · `[P]` pending investigation

- [~] [override-expansion](./tasks/override-expansion.md) Support richer proxy tool overrides (descriptions, aliases) so agents see our tuned guidance during initialize/tools/list results.
- [x] [user-config-overlays](./tasks/user-config-overlays.md) Split repo-shipped defaults from per-instance overlays (e.g. `~/.config/stelae`) so clones stay generic while local MCP customisations auto-load outside git.
- [x] [scrapling-mcp-output-schema](./tasks/scrapling-mcp-output-schema.md) Resolve Scrapling MPC schema mismatches via the shim + override automation.
- [x] [tool-override-population](./tasks/tool-override-population.md) Auto-populate default `inputSchema`/`outputSchema` entries when new MCP servers are added, keeping overrides ready for on-demand shims.
- [x] [shim-schema-retry](./tasks/shim-schema-retry.md) (prereq: tool-override-population) Teach the shim to attempt schema-specific wrapping before falling back to the generic adapter.
- [x] [mcp-auto-loading](./tasks/mcp-auto-loading.md) Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides (with guardrails).
- [x] [docy-source-manager](./tasks/docy-source-manager.md) Manage the Docy URL catalog via a dedicated MCP tool so resources stay editable and visible through MCP alone.
- [~] [tool-overrides-schema-cleanup](./tasks/tool-overrides-schema-cleanup.md) Normalize tool override schema/automation with validation + per-server entries to eliminate drift and duplication.
- [x] [tool-aggregations](./tasks/tool-aggregations.md) Add declarative tool aggregation helper + config to expose composite tools while hiding noisy downstream entries.
- [x] [local-runtime-hardening](./tasks/local-runtime-hardening.md) Fix overlay regressions, add local-only runtime coverage, and strengthen generic-vs-local config hygiene.
- [ ] [repo-maintenance-pass](./tasks/repo-maintenance-pass.md) Refresh architecture/docs, consolidate config helpers, and add a repo hygiene verification workflow.

## Action Items

- [x] Remove legacy Python shim (scripts/mcp_output_shim.py) and all references from docs/templates. Keep only proxy call-path adapter; confirm no server routes through shim; update README and ARCHITECTURE accordingly.
- [ ] Create a `dev/tasks/*_task_dependencies.json` map if future work introduces enough parallel tasks to benefit from explicit DAG tracking.
