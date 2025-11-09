# Stelae Tool Aggregation Plan

This note captures the current `tools/list` snapshot from the running proxy (queried 2025-02-14 via `curl http://127.0.0.1:9090/mcp`) and the consolidation plan that balances catalog clarity with the flexibility described in `README.md` and `docs/ARCHITECTURE.md`.

## Current Catalog Snapshot

| Primary server | Tool count | Key capabilities |
| --- | --- | --- |
| `fs` | 23 | Directory listings, metadata, searches, file edits, archive helpers |
| `mem` | 18 | Basic Memory note/project lifecycle, search, context rebuild |
| `sh` | 8 | Terminal controller for guarded shell commands + file patch helpers |
| `one_mcp` | 7 | 1mcp CLI helpers (plan, fetch README, config scaffolding) |
| `strata` | 5 | Strata discovery + action execution flow |
| `docs` | 3 | Docy fetch (`fetch_document_links`, `fetch_documentation_page`, `list_documentation_sources_tool`) |
| `scrapling` | 2 | `s_fetch_page`, `s_fetch_pattern` (web fetch modes) |
| `docy_manager` | 1 | `manage_docy` (already wrapped by `manage_docy_aggregate`) |
| `integrator` | 1 | `manage_stelae` (integrates 1mcp discovery) |
| `fetch` | 1 | Canonical HTTP fetch |
| `rg` | 1 | `grep` via ripgrep |
| `facade` | 1 | `search` placeholder (for legacy connector checks) |

71 tools are exposed today; most surface area is concentrated in the workspace filesystem (`fs` + `sh` overlaps) and Basic Memory servers. Without consolidation the manifest is noisy, which in turn makes it harder for agents to pick the right primitive on the first try.

## Aggregation Strategy

The goal is "one conceptual tool per domain" without hiding useful functionality. Each aggregate accepts an `operation` selector and forwards strongly-typed parameters to the underlying tool, so existing schemas remain authoritative. The following suites now live in `config/tool_aggregations.json`:

1. **`workspace_fs_read`** – Read-only filesystem helpers (`list_*`, `read_*`, `find_*`, `search_*`, `calculate_directory_size`, `get_file_info`). Annotated with `readOnlyHint` to reinforce safe access.
2. **`workspace_fs_write`** – Mutating filesystem actions (`create_directory`, `move_file`, `edit_file`, `write_file`, `delete_file_content`, `insert_file_content`, `update_file_content`, `zip_*`, `unzip_file`). Tagged `destructiveHint` so connectors treat it carefully.
3. **`workspace_shell_control`** – Terminal controller primitives (`execute_command`, `change_directory`, `get_current_directory`, `get_command_history`). Keeps process-control chatter out of the main catalog while preserving guardrails.
4. **`memory_suite`** – All 18 Basic Memory tools (context build, CRUD for notes/projects, search, project switching). Gives agents a single entry point for long-term memory work.
5. **`doc_fetch_suite`** – Docy fetch helpers (links, full pages, catalog listing). Complements `manage_docy_aggregate` without surfacing three near-identical fetchers.
6. **`scrapling_fetch_suite`** – Wraps `s_fetch_page` and `s_fetch_pattern` so the manifest only advertises “Scrapling Fetch” once while retaining the mode switch.
7. **`strata_ops_suite`** – Consolidates Strata’s discovery/execution/auth failure workflows so routing logic feels atomic.
8. **Existing** **`manage_docy_aggregate`** – Left untouched; still governs Docy catalog administration.

Single-tool servers (`fetch`, `rg`, `manage_stelae`) stay as-is because an extra layer would not shrink the manifest further.

## Hidden/Retired Tools

- `manage_docy` (docy_manager) remains hidden behind `manage_docy_aggregate`.
- All direct filesystem, shell, memory, doc, scrapling, and strata tools are now hidden via the aggregate entries above. This keeps the manifest small but still lets the aggregator proxy fan-out the calls.
- `one_mcp` helpers (`configure_mcp_plan`, `deep_search_planning`, `fetch_readme`, `file_system_config_setup`, `find_mcp_config_path_path`, `quick_search`, `validate_mcp_config_content`) are hidden at the config level because `integrator.manage_stelae` already orchestrates 1mcp flows end-to-end per README guidance.
- `facade.search` is hidden; we no longer need the placeholder verification hook now that Docy/Scrapling provide canonical fetch/search.

`dev/tools_list_snapshot.json` captures the raw discovery payload used for this pass so future updates can diff against a known baseline.

## How to Apply the Aggregations

1. **Validate + render**
   ```bash
   python3 scripts/process_tool_aggregations.py --check-only
   python3 scripts/process_tool_aggregations.py
   make render-proxy
   ```
2. **Restart & verify**
   ```bash
   scripts/run_restart_stelae.sh --full
   curl -s http://127.0.0.1:9090/mcp -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":"tools","method":"tools/list"}' | jq '.result.tools[].name'
   ```
   Expect only the aggregates + singleton servers (fetch, grep, manage_stelae, etc.) to remain.
3. **Regression checks**
   - Spot-check a few aggregated operations (e.g., `workspace_fs_read` → `read_file`) to confirm argument routing.
   - Run `pytest` if any downstream scripts were touched.

## Follow-up Ideas

- Add schema-aware docs (examples per operation) to each aggregate once agents have exercised them a bit; this keeps the `operation` enum discoverable.
- Consider pulling Docy/documentation surfacing into Strata if we introduce more advanced routing, so there’s a single “knowledge ops” entry.
- If future MCP servers land (e.g., additional diagnostics), follow the same pattern: snapshot tools, decide whether they belong in an existing suite or warrant a new aggregate, and run the renderer/update cycle.
