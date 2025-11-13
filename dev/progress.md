---
doc-type: progress
name: stelae Progress Tracker
tags: [project, progress]
status: draft
last_updated: 2025-11-12
---

# Stelae Progress Tracker

Legend: `[x]` done · `[~]` in progress · `[ ]` not started · `[!]` broken · `[?]` verify · `[P]` pending investigation

- [ ] [clone-smoke-harness-stability](./tasks/stelae-smoke-readiness.md#harness--restart-reliability) Stabilize the Codex clone smoke harness (auto + manual-stage flows) so bundle install/render/restart finish with live output in <60 s and the full e2e run produces transcripts + clean git status in a fresh sandbox.
- [~] [stelae-mcp-catalog-consistency](./tasks/stelae-smoke-readiness.md#catalog-hygiene) Ensure the Stelae MCP proxy consistently advertises the curated tool suite and that Codex (CLI + wrapper) can discover/call those tools without manual fallbacks. *(2025-11-12: fresh `codex exec --json --full-auto` run in `logs/codex-catalog-orchestrator-latest.jsonl` shows `workspace_fs_read` succeeding again; need to wire the remaining tool calls + harness assertions.)*
- [x] [stelae-tool-aggregation-visibility](./tasks/stelae-smoke-readiness.md#catalog-hygiene) Keep the tool aggregation overrides/manifest deduped so only the aggregate entries appear in `tools/list` and their schemas remain valid for Codex registration.
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
- [x] [core-stack-modularization](./tasks/core-stack-modularization.md) Ship a minimal core stack plus an optional starter bundle so clones stay lightweight while power users can opt into the full tool suite.
- [x] Deliver a Codex MCP wrapper (sandbox/missions interface) so agents can be launched programmatically for QA flows. Repo lives at `~/dev/codex-mcp-wrapper` with health probes, persistent session routing, artifact bundling, release builder, starter-bundle wiring, and an automated MCP smoke test in this repo.
- [x] Add a fully-automatic clone smoke test (Codex CLI + sandbox harness with manual fallback) so the “self-managing MCP server” promise is regularly validated.
- [ ] Refresh all integrated MCP servers (core + starter bundle) to the latest compatible versions and update overrides/docs as needed.
- [ ] [1mcp-server-separation](./tasks/1mcp-server-separation.md) Align the forked `1mcp-server` repo with upstream hygiene while making AI/API integrations optional so offline clones avoid extra dependencies.
- [x] [repo-maintenance-pass](./tasks/repo-maintenance-pass.md) Refresh architecture/docs, consolidate config helpers, and add the `make verify-clean` workflow so render/restart automation keeps `git status` clean.

## Action Items

> Not for tasks (which live above), these are to be launched should a prerequesite be met, rather than completed in sequence

- [x] Remove legacy Python shim (scripts/mcp_output_shim.py) and all references from docs/templates. Keep only proxy call-path adapter; confirm no server routes through shim; update README and ARCHITECTURE accordingly.
- [ ] Create a `dev/tasks/*_task_dependencies.json` map if future work introduces enough parallel tasks to benefit from explicit DAG tracking.
