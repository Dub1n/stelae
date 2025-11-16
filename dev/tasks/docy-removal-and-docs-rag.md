# Task: Remove Docy stack and stage new documentation catalog/RAG pipeline

Related requirement: `docs/current/progress.md` → Stelae Proxy Hardening → "Documentation catalog must be vendor-agnostic and live entirely outside tracked templates".

Tags: `#infra` `#docs`

## Checklist

- [x] Phase 1: Remove Docy from tracked repo and starter bundle (scripts, templates, README/tests).
- [ ] Phase 2: Refactor aggregates/state helpers to support doc catalog state (`documentation_catalog` aggregate, `${STELAE_STATE_HOME}/doc_catalog.json`).
- [ ] Phase 3: Install/validate new MCP stack (Tavily search/fetch + Qdrant RAG baseline; add optional fetch fallbacks if needed).
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: replace doc catalog stack` after tests.

## References

- Code:
  - `scripts/docy_manager_server.py`, `scripts/render_docy_sources.py`, `config/docy_sources.json`, `.docy.urls` (to delete/relocate).
  - `config/bundles/starter_bundle.json` (remove docy servers + aggregates, add new aggregate definition later).
  - `scripts/tool_aggregator_server.py`, `stelae_lib/integrator/tool_aggregations.py`, `stelae_lib/integrator/stateful_runner.py` (ensure state helper covers new aggregate fields).
  - `README.md`, `docs/ARCHITECTURE.md`, `tests/test_docy_manager.py`, `tests/test_docy_sources.py`, `tests/test_tool_aggregations.py` (Docy-specific cases to retire or rewrite).
- Tests:
  - `pytest tests/test_tool_aggregations.py`, `tests/test_streamable_mcp.py`, `tests/test_docy_manager.py`, `tests/test_docy_sources.py`.
- Docs:
  - `README.md` (Stack Snapshot + Docy sections), `docs/ARCHITECTURE.md`, `dev/tasks/docy-source-manager.md`, `docy_replacement_brief.md` (new research summary).

## Notes

### Phase 1 – Remove Docy stack entirely ✅

Completed:

1. Deleted every Docy-specific asset (manager/renderer scripts, catalog template, `.docy.urls`, helper libs, tests, task logs) and scrubbed tracked docs plus starter bundle references.
2. Updated starter bundle + overrides to drop `docy_manager`, `docs`, `manage_docy_sources`, and `doc_fetch_suite`, replacing tests/helpers with neutral “sample fetch suite” fixtures.
3. Scrubbed README/ARCHITECTURE/AGENTS/TODO/harness docs along with the smoke harness, missions, and tooling logs so the remaining text covers the upcoming vendor-neutral documentation flow.
4. Adjusted aggregator/runtime tests and reran `pytest tests/test_tool_aggregations.py tests/test_streamable_mcp.py` to confirm the baseline still passes without Docy.

### Phase 2 – Prep new aggregate/state plumbing

1. Define `documentation_catalog` aggregate JSON (input schema w/ operations: `search`, `curate_add`, `curate_remove`, `curate_list`, `fetch`, `rag_index`, `rag_query`).
2. Attach state definition pointing to `${STELAE_STATE_HOME}/doc_catalog.json` (fields: `savedSources`, `recentSearches`, `defaultEngine`, etc.).
3. Update tool aggregator schema/tests to cover the new state-backed rules (preloads/mutations/responses) so no Python changes are needed later.
4. Document the aggregate in README/ARCHITECTURE and add a dev note describing how to extend state definitions.

### Phase 3 – Integrate new MCP servers after baseline

1. Install Tavily MCP (HTTP endpoint) via `manage_stelae install_server`; hydrate env var placeholders for `TAVILY_API_KEY`.
2. Install Qdrant MCP (stdio) in local mode (no cloud API) with storage under `${STELAE_STATE_HOME}/qdrant`. If offline mode is insufficient, fall back to Chroma MCP.
3. Wire `documentation_catalog` aggregate to call Tavily search/extract + Qdrant store/find. Keep optional fetch fallbacks (Scrapling, mcp-server-fetch) ready but add after MVP proves stable.
4. Regression-pass: `pytest`, `make verify-clean`, targeted tool calls (search/fetch/rag) through the proxy.

### Follow-ups

- After MVP, consider layering Brave/Firecrawl/Scrapling search/fetchers as alternative engines using aggregate selectors.
- Update bundle installer to optionally install Tavily + Qdrant + aggregate entries when `starter_bundle` is requested.
- Remove legacy docy task doc (`dev/tasks/docy-source-manager.md`) once new stack is live.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
