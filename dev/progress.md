---
doc-type: progress
name: stelae Progress Tracker
tags: [project, progress]
status: draft
last_updated: 06-11-2025
---

# Stelae Progress Tracker

Legend: `[x]` done · `[~]` in progress · `[ ]` not started · `[!]` broken · `[?]` verify · `[P]` pending investigation

## Requirement Group A

- [~] [override-expansion](./tasks/override-expansion.md) Support richer proxy tool overrides (descriptions, aliases) so agents see our tuned guidance during initialize/tools/list results.
- [x] [scrapling-mcp-output-schema](./tasks/scrapling-mcp-output-schema.md) Resolve Scrapling MPC schema mismatches via the shim + override automation.
- [x] [tool-override-population](./tasks/tool-override-population.md) Auto-populate default `inputSchema`/`outputSchema` entries when new MCP servers are added, keeping overrides ready for on-demand shims.
- [x] [shim-schema-retry](./tasks/shim-schema-retry.md) (prereq: tool-override-population) Teach the shim to attempt schema-specific wrapping before falling back to the generic adapter.
- [ ] [mcp-auto-loading](./tasks/mcp-auto-loading.md) Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides (with guardrails).
- [~] Another requirement

## Requirement Group B

- [x] Completed requirement.
- [!] Broken requirement (brief note + task log).

## Action Items

- Summarise next steps or coordination needs.
- [ ] Remove legacy Python shim (scripts/mcp_output_shim.py) and all references from docs/templates. Keep only proxy call-path adapter; confirm no server routes through shim; update README and ARCHITECTURE accordingly.
