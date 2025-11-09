# Task: Docy Source Manager MCP Tool

Related requirement: `dev/progress.md` → Stelae Progress Tracker → "Docy sources manageable via MCP".

Tags: `#automation` `#infra` `#mcp`

## Checklist

- [x] Define canonical Docy catalog schema (`config/docy_sources.json`) with metadata (url, title, tags, refresh hints).
- [x] Build a renderer (`scripts/render_docy_sources.py`) that converts the catalog into `.docy.urls` atomically (no service restart required).
- [x] Implement a dedicated Docy MCP server exposing one tool (e.g., `manage_docy`) whose `operation` enum covers `list_sources`, `add_source`, `remove_source`, `sync_cache`, `dry_run`.
- [x] Add CLI parity so humans/batch jobs can run the same dispatcher outside MCP.
- [x] Document the workflow (README + docy task log references) and update progress/task logs; include tests covering catalog edits and renderer output.

## References

- Code: `config/docy_sources.json` (new), `scripts/render_docy_sources.py` (new), `scripts/docy_manager_server.py` (new).
- Tests: `tests/test_docy_manager.py` (new).
- Docs: README “Docy sources” section (new) + `dev/tasks/docy-source-manager.md` (this file).

## Notes

- Docy watches `.docy.urls` live, so we avoid restarts; just rewrite the catalog and (optionally) trigger a background cache sync.
- Keep the tool list minimal by exposing a single Docy-specific MCP tool with discriminated `operation` payloads—aligns with the stelae-integrator approach while keeping per-server responsibilities isolated.
- Future extension: add `import_from_manifest` to seed Docy from 1mcp discovery entries once stabilized. *Completed 2025-11-09 — `manage_docy` now accepts `{"operation": "import_from_manifest"}` with `manifest_path`/`manifest_url`, optional tags, and `dry_run` so the Docy catalog can be hydrated directly from discovery cache or remote manifests.*

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] progress.md updated
- [x] Task log updated
- [x] Checklist completed
