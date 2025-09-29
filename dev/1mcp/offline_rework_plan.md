# 1mcp Offline Rework Plan

Author: Codex assistant  
Date: $(date -I)

## 1. Context & Current State

- **Upstream repo**: `particlefuture/1mcpserver` installed under `~/apps/vendor/1mcpserver` (tracked via `uv`).
- **Runtime dependency**: `server.py` initialises `OpenAIEmbeddings()` unconditionally and loads/creates a FAISS index (`db/faiss_index`). Missing `OPENAI_API_KEY` causes a hard failure at import time.
- **Tool surface**: `quick_search`, `deep_search_planning`, `fetch_readme`, etc. expect an in-memory vector store that returns `{name, description, url}` triples from `db/server_list.db`.
- **Data source**: `scrape.py` rebuilds `db/server_list.db` and the FAISS index from curated GitHub lists. Embedding generation is irreducibly tied to OpenAI in the current implementation.
- **Stelae integration**: Proxy template adds a `one_mcp` stdio stanza that shells into `uv --directory ... run server.py --local`. No additional environment is attached inside PM2 yet.

## 2. Goal

Create a fork (e.g. `github.com/<user>/1mcpserver`) with a branch that:

1. Eliminates all external AI dependencies (OpenAI, FAISS, LangChain) at runtime and in packaging metadata.
2. Provides a deterministic, fully offline search backend over the existing SQLite corpus.
3. Preserves the public API (tools, prompts, CLI entry points) so Stelae can consume it without further schema changes.
4. Documents the new behaviour and provides lightweight regression coverage.

## 3. Constraints & Design Principles

- No outbound network/API calls during server startup or query handling.
- Keep the DB rebuild tooling functional without OpenAI; if vector search quality drops, document that the lexical scorer is “good enough” and deterministic.
- Avoid scattering feature flags in client code; prefer a clean replacement module over intertwined conditionals.
- Ensure the fork remains vendorable via `uv` (use `pyproject.toml` semantics the tooling expects).
- Align with Stelae conventions (≤150-line modules, typed helpers, explicit env knobs).

## 4. Target Architecture

### 4.1 Search Backend

- Introduce a new module `search_backend.py` (or similar) housing:
  - `ServerRecord` dataclass (`name`, `description`, `url`, `tokens`).
  - Loader that reads `db/server_list.db` once at startup and tokenises descriptions using a simple regex (`re.findall(r"[a-z0-9]+", text.lower())`).
  - Scoring function combining Jaccard similarity and `difflib.SequenceMatcher` to rank query vs. description.
  - `search(query, top_k)` returning the same structure `[{"name": ..., "description": ..., "url": ...}, ...]`.
- `server.py` imports `search_backend` instead of `langchain_openai` / FAISS. `vector_store_search` becomes a thin wrapper around `search_backend.search`.

### 4.2 Optional CLI Sync

- If we want to keep a high-quality index, allow an optional `USE_VECTORS=1` environment toggle that (only when the dependencies exist **and** the env var is set) re-enables the FAISS path.
- Default behaviour must be offline even if the dependencies remain installed.
- Given the quality vs. simplicity trade-off, default plan is to *remove* FAISS entirely unless the user explicitly pushes to keep it.

### 4.3 Packaging Cleanup

- `pyproject.toml`:
  - Drop `faiss-cpu`, `langchain`, `langchain-openai`, `langchain-community`, `langchain-text-splitters`, `openai`, `google-auth`, any transitive-only packages tied to embeddings.
  - Audit remaining deps; keep only what the server uses (FastAPI, fastmcp, sqlite, requests, PyGithub, etc.).
- Regenerate `uv.lock`.

### 4.4 Documentation & DX

- README: update setup instructions (no API keys, mention offline search backend and optional re-scrape flow).
- Add a CHANGELOG entry or `docs/offline.md` summarising rationale.
- Include a migration note for prior consumers (e.g. “if you relied on vector search quality, set `USE_VECTORS=1` and add your own embedding backend”).

### 4.5 Tests & Verification

- Create basic tests under `tests/` (new folder) covering:
  - Tokeniser behaviour.
  - Ranking consistency for known queries (use a subset of rows seeded in a fixture or an in-memory sqlite DB).
  - `quick_search` returning deterministic results without env vars.
- Add a smoke target (e.g. `uv run python -m tests`) to README.

## 5. Task Breakdown

1. **Fork & Branch Prep**
   - Fork `particlefuture/1mcpserver` to the user’s GitHub account.
   - Create branch `offline-search` (or similar).
   - Update Stelae vendoring to track the fork (`git remote set-url` or reclone into `~/apps/vendor/1mcpserver`).

2. **Dependency Audit**
   - Remove unused packages from `pyproject.toml`.
   - Run `uv sync` and ensure lock regeneration.

3. **Backend Refactor**
   - Add `search_backend.py` with loader, tokeniser, scoring.
   - Update `server.py` to use the new backend (delete FAISS/OpenAI init, adjust `vector_store_search`).
   - Remove dead code (imports, `OpenAIEmbeddings`, fallback logic, `vector_store` global).

4. **Scrape Script Update**
   - Adjust `scrape.py` to reuse the new backend or emit plain DB rows without embeddings.
   - Confirm the script still writes `db/mcp_servers.txt`, refreshes SQLite, and logs summary.

5. **Docs & Metadata**
   - Refresh README (setup steps, environment notes).
   - Add change log / docs entry.

6. **Testing**
   - Introduce tests and wire them into a lightweight CI instruction (manual for now).
   - Run `uv run pytest` (or `python -m pytest`) locally.

7. **Integration in Stelae**
   - Point `.env` / `config/proxy.template.json` to the forked path if it changes.
   - Remove `OPENAI_API_KEY` / `GITHUB_TOKEN` placeholders from `.env.example` if no longer required.
   - Verify `pm2 restart mcp-proxy` launches the child without env overrides.

8. **Upstream Coordination (Optional)**
   - Consider PR back upstream with feature flag; ensure license compatibility.
   - Document divergence in `dev/1mcp/README.md` for future maintainers.

## 6. Open Questions / Decision Points

- **Quality vs. simplicity**: Do we retain an optional vector path behind a flag or remove it entirely? (Default plan: remove; revisit if ranking proves too weak.)
- **Data updates**: Should we schedule periodic re-scrapes, or accept the static DB? (For now, keep existing `scrape.py` but make sure it doesn’t require embeddings.)
- **Publishing**: Will we tag releases from the fork? If yes, set up a naming convention (e.g. `offline-v0.2.0`).

## 7. Acceptance Criteria

- `uv run server.py --local` starts cleanly with no env vars set.
- `quick_search("filesystem")` returns a stable list of entries.
- Tests exercise the new backend and pass.
- Stelae proxy exposes the `one_mcp` server without additional env configuration, and manifests list the tool.
- Documentation reflects the offline-first behaviour.

