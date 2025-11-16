# Task: Retire the legacy documentation stack and stage the new documentation catalog/RAG pipeline

Related requirement: `docs/current/progress.md` → Stelae Proxy Hardening → "Documentation catalog must be vendor-agnostic and live entirely outside tracked templates".

Tags: `#infra` `#docs`

## Checklist

- [x] Phase 1: Remove the legacy documentation stack from the tracked repo and starter bundle (scripts, templates, README/tests).
- [ ] Phase 2: Refactor aggregates/state helpers to support doc catalog state (`documentation_catalog` aggregate, `${STELAE_STATE_HOME}/doc_catalog.json`).
- [ ] Phase 3: Install/validate new MCP stack (Tavily search/fetch + Qdrant RAG baseline; add optional fetch fallbacks if needed).
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: replace doc catalog stack` after tests.

## References

- Code:
  - Legacy documentation manager/renderers/catalog templates (already removed) plus the new documentation catalog state helpers.
  - `config/bundles/starter_bundle.json` (ensure documentation/catalog servers remain optional and clean).
  - `scripts/tool_aggregator_server.py`, `stelae_lib/integrator/tool_aggregations.py`, `stelae_lib/integrator/stateful_runner.py` (ensure state helpers cover new aggregate fields).
  - `README.md`, `docs/ARCHITECTURE.md`, tests covering the documentation catalog aggregate and fetch suite (now replacing the legacy stack).
- Tests:
  - `pytest tests/test_tool_aggregations.py`, `tests/test_streamable_mcp.py`, plus any new documentation catalog unit tests.
- Docs:
  - `README.md` (Stack Snapshot + documentation sections), `docs/ARCHITECTURE.md`, and `dev/notes/documentation_catalog_replacement_brief.md` (research summary).

## Notes

### Phase 1 – Remove the legacy documentation stack entirely ✅

Completed:

1. Deleted every legacy documentation-specific asset (manager/renderer scripts, catalog template, URL caches, helper libs, tests, task logs) and scrubbed tracked docs plus starter bundle references.
2. Updated starter bundle + overrides to drop the legacy documentation servers (catalog manager + fetch suite) and aggregates, replacing tests/helpers with neutral “sample fetch suite” fixtures.
3. Scrubbed README/ARCHITECTURE/AGENTS/TODO/harness docs along with the smoke harness, missions, and tooling logs so the remaining text covers the upcoming vendor-neutral documentation flow.
4. Adjusted aggregator/runtime tests and reran `pytest tests/test_tool_aggregations.py tests/test_streamable_mcp.py` to confirm the baseline still passes after removing the legacy stack.

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
- Remove the legacy documentation task doc once the new stack is live.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
