got it—here’s the landscape + a practical swap plan to retire the legacy documentation MCP without losing capability. ✧⁠◝⁠(⁠⁰⁠▿⁠⁰⁠)⁠◜⁠✧

> context (what we’re replacing)
>
> stelae previously shipped a legacy documentation MCP plus a small manager and wrapped it behind aggregated tools (`documentation_catalog`, `doc_fetch_suite`), with aggregates allowed to persist JSON state under `${STELAE_STATE_HOME}`. those bespoke assets are now removed from git, and the goal is to lean on off‑the‑shelf mcp servers with curated lists/history stored in a state file like `${STELAE_STATE_HOME}/doc_catalog.json` and exposed via a new aggregate (e.g., `documentation_catalog`).

---

## shortlist (recommended combos)

**option a — one-box search+fetch, with optional rag**

* **tavily mcp** (search, map, crawl, extract) + **qdrant mcp** *or* **chroma mcp** for rag. ([GitHub][1]) ([GitHub][2]) ([GitHub][3])

**option b — composable**

* **brave search mcp** (rich search + summarizer) → **mcp‑server‑fetch** (markdown fetch) → **scrapling mcp** (stealth/dynamic pages) → **qdrant/chroma** for rag. ([GitHub][4]) ([PyPI][5]) ([scrapling.readthedocs.io][6]) ([GitHub][2])

either path keeps curated lists/history in your aggregate’s JSON state under `${STELAE_STATE_HOME}`; nothing tied to the retired documentation stack remains in the repo.

---

## candidates (details you can copy into `manage_stelae` descriptors)

> each card below covers: repo/url + install, tools/ops, built‑in persistence, deps, and how it maps to your `documentation_catalog` aggregate.

### 1) tavily mcp — **search + fetch + crawl** (hosted or local)

* **repo / install**

  * remote (http): `url: https://mcp.tavily.com/mcp/?tavilyApiKey=YOUR_KEY` (works directly as an http mcp server). local: `npx -y tavily-mcp@latest`. ([GitHub][7])
* **tools/ops**
  `search` (web), `extract` (parse url to text/markdown), `map` (site exploration), `crawl` (follow links). ([GitHub][7])
* **persistence**
  no built‑in catalog/bookmarks; you’ll store curated lists in `${STELAE_STATE_HOME}/doc_catalog.json`. (fits your state helper.)
* **deps**
  `TAVILY_API_KEY`. transport: http or stdio via npx. ([GitHub][7])
* **aggregate mapping**

  * `documentation_catalog.search` → `tavily.search`
  * `documentation_catalog.fetch` → `tavily.extract` (or `crawl`/`map` for multi‑page)
  * curated add/remove/list → state json (no server CRUD).

### 2) exa mcp — **search + contents + deep researcher**

* **repo / install**

  * remote (http): `https://mcp.exa.ai/mcp?exaApiKey=YOUR_KEY` (can enable specific tools via `tools=` param). local: `npx -y exa-mcp-server`. ([docs.exa.ai][8])
* **tools/ops**
  `web_search_exa`, `get_code_context_exa`, `crawling_exa`, `company_research_exa`, `linkedin_search_exa`, `deep_researcher_start`/`check`. ([docs.exa.ai][8])
* **persistence**
  exa has “websets” at the platform level, but the mcp page emphasizes search/crawling/deep‑research; treat curated sources as aggregator state. ([docs.exa.ai][8])
* **deps**
  `EXA_API_KEY`. http or npx stdio. ([docs.exa.ai][8])
* **aggregate mapping**
  same as tavily; optionally expose `deep_researcher_*` as a long‑running “research mode.”

### 3) brave search mcp — **rich search + summaries**

* **repo / install**

  * `npx -y @brave/brave-search-mcp-server` (defaults to **stdio**). set `--transport http` or `BRAVE_MCP_TRANSPORT=http` for http. docker image available. ([GitHub][9])
* **tools/ops**
  `brave_web_search`, `brave_local_search`, `brave_video_search`, `brave_image_search`, `brave_news_search`, `brave_summarizer` (requires summary key from web search with `summary: true`). ([GitHub][9])
* **persistence**
  none (you’ll use aggregator state).
* **deps**
  `BRAVE_API_KEY`; node 22+ if building locally. stdio/http. ([GitHub][9])
* **aggregate mapping**
  `search` → brave; **pair with** `mcp‑server‑fetch` or `scrapling` for retrieval.

### 4) firecrawl mcp — **crawl + extract + search (self‑host or cloud)**

* **docs / install**

  * local stdio: `npx -y firecrawl-mcp`
  * remote http: set `HTTP_STREAMABLE_SERVER=true` and run with port/host; also supports `FIRECRAWL_API_KEY` against their hosted api. ([Firecrawl][10])
* **tools/ops**
  `search`, `map` (explore a site), `crawl`, `extract/scrape` (markdown+metadata). ([Firecrawl][10])
* **persistence**
  no built‑in catalog; use aggregator state.
* **deps**
  optional `FIRECRAWL_API_KEY`; otherwise self‑hostable. stdio/http (streamable). ([Firecrawl][10])
* **aggregate mapping**
  single server can handle both `search` and `fetch` for many sites.

### 5) scrapling mcp — **stealth/dynamic fetch (cloudflare, js‑heavy)**

* **docs / install**

  * `pip install "scrapling[ai]" && scrapling install` (browser deps)
  * run: `scrapling mcp` (stdio) or `scrapling mcp --http` (http). docker image available. ([scrapling.readthedocs.io][11])
* **tools/ops**
  `get`, `bulk_get`, `fetch` (headless), `bulk_fetch`, `stealthy_fetch`/`bulk_stealthy_fetch` (cloudflare/turnstile bypass), css‑selector extraction to reduce tokens. ([scrapling.readthedocs.io][11])
* **persistence**
  none; use aggregator state.
* **deps**
  chromium via `scrapling install`; optional proxies. ([scrapling.readthedocs.io][11])
* **aggregate mapping**
  fallback retriever when `fetch` fails or content is dynamic/protected.

### 6) mcp‑server‑fetch — **simple, fast url→markdown**

* **repo / install**

  * `pip install mcp-server-fetch` → run with `python -m mcp_server_fetch`, or `uvx mcp-server-fetch`, or docker `mcp/fetch`. proxy support via `--proxy-url`. ([PyPI][5])
* **tools/ops**
  `fetch(url)` → markdown; chunking via `start_index`. ([PyPI][5])
* **persistence**
  none; use aggregator state.
* **deps**
  none; optional node present improves html simplifier. ([PyPI][5])
* **aggregate mapping**
  first‑try retriever for normal pages.

### 7) duckduckgo mcp — **keyless search + basic fetch**

* **repo / install**

  * `uv pip install duckduckgo-mcp-server` or `npx -y @smithery/cli install @nickclyde/duckduckgo-mcp-server --client claude` (stdio). ([GitHub][12])
* **tools/ops**
  `search(query)`, `fetch_content(url)` with sensible rate‑limits + llm‑friendly formatting. ([GitHub][12])
* **persistence**
  none; use aggregator state.
* **deps**
  no api key required. ([GitHub][12])
* **aggregate mapping**
  budget‑friendly search; pair with `fetch`/`scrapling`.

### 8) serper (google) mcp — **google‑style search + scrape**

* **repo / install**

  * `npx -y serper-search-scrape-mcp-server` (stdio/http via node), docker image available. ([GitHub][13])
* **tools/ops**
  `google_search` (supports `site:`, `filetype:`, `before:/after:` etc.), `scrape` (plaintext/markdown + metadata). ([GitHub][13])
* **persistence**
  none; use aggregator state.
* **deps**
  `SERPER_API_KEY`. ([GitHub][13])
* **aggregate mapping**
  swap-in alternative when you want google‑style operators.

### 9) qdrant mcp — **rag store (vector)**

* **repo / install**

  * `uvx mcp-server-qdrant` (stdio by default). supports `--transport sse` or `--transport streamable-http`; docker supported. ([GitHub][14])
* **tools/ops**
  `qdrant-store` (add text+metadata), `qdrant-find` (semantic search). uses FastEmbed by default. ([GitHub][14])
* **persistence**
  **yes** — it’s your kb. configure `QDRANT_URL`/`QDRANT_API_KEY` or `QDRANT_LOCAL_PATH`. ([GitHub][14])
* **deps**
  qdrant server (self‑host or cloud), embedding model envs. ([GitHub][14])
* **aggregate mapping**
  `documentation_catalog.index` → `qdrant-store`; `documentation_catalog.query_kb` → `qdrant-find`.

### 10) chroma mcp — **rag store (vector + text search)**

* **repo / install**

  * `uvx chroma-mcp` (ephemeral or persistent), or http/chroma cloud via flags/env. ([GitHub][15])
* **tools/ops**
  rich collection mgmt; `chroma_add_documents`, `chroma_query_documents`, full‑text + vector + metadata filters. supports multiple embedding providers via env. ([GitHub][15])
* **persistence**
  **yes** — file‑backed, http, or cloud. ([GitHub][15])
* **deps**
  chroma local/cloud, optional embedding api keys. ([GitHub][15])
* **aggregate mapping**
  same as qdrant; pick the store you prefer operationally.

---

## capability coverage matrix (quick read)

| server           | search                       | fetch/scrape                   | crawl/map | rag store | http/stdio                               |
| ---------------- | ---------------------------- | ------------------------------ | --------- | --------- | ---------------------------------------- |
| tavily           | ✅                            | ✅ (`extract`)                  | ✅         | —         | both ([GitHub][7])                       |
| exa              | ✅                            | ✅ (`crawling`/contents)        | ✅         | —         | both ([docs.exa.ai][8])                  |
| brave search     | ✅ (+news/images/local/video) | (summary only; not full fetch) | —         | —         | both ([GitHub][9])                       |
| firecrawl        | ✅                            | ✅                              | ✅         | —         | both (streamable http) ([Firecrawl][10]) |
| duckduckgo       | ✅                            | ✅ (basic)                      | —         | —         | stdio (python) ([GitHub][12])            |
| mcp‑server‑fetch | —                            | ✅                              | —         | —         | both (docker/python) ([PyPI][5])         |
| scrapling        | —                            | ✅ (stealth/js)                 | —         | —         | both ([scrapling.readthedocs.io][11])    |
| qdrant           | —                            | —                              | —         | ✅         | stdio/sse/http ([GitHub][14])            |
| chroma           | —                            | —                              | —         | ✅         | stdio/http/cloud ([GitHub][15])          |

---

## how this maps to stelae (aggregate + state)

**aggregate name:** `documentation_catalog`
**state file:** `${STELAE_STATE_HOME}/doc_catalog.json` (history + curated list) — aligns with your overlay→runtime design: tracked templates remain read‑only; aggregates can declare json‑backed state under `${STELAE_STATE_HOME}`.

**proposed operations**

* `search(query, site?, engine?)` → routes to **tavily**/**exa**/**brave**/**ddg** based on `engine` param or default policy.
* `curate.add(entry)` / `curate.remove(id)` / `curate.list()` → maintained entirely in the state json (no custom scripts needed thanks to your `StatefulAggregatedToolRunner`).
* `fetch(url, mode?)` → try `mcp‑server‑fetch` first; if blocked or dynamic, fall back to `scrapling` (stealth) or `firecrawl` (crawl/extract).
* `rag.index(doc_id|url|raw, kb=default)` → push normalized text+metadata into **qdrant** or **chroma**.
* `rag.search(query, kb=default)` → semantic search from the chosen store.

**env + install flow**
use `manage_stelae` to add servers; new env keys land in `${STELAE_CONFIG_HOME}/.env.local` so the repo stays clean, consistent with your current integrator workflow.  

---

## install one‑liners you can drop into descriptors

> **searchers**

* **tavily (http)**
  `url: https://mcp.tavily.com/mcp/?tavilyApiKey={{TAVILY_API_KEY}}` ([GitHub][7])
* **exa (http)**
  `url: https://mcp.exa.ai/mcp?exaApiKey={{EXA_API_KEY}}&tools=web_search_exa,crawling_exa` ([docs.exa.ai][8])
* **brave (stdio)**
  `command: npx`, `args: ["-y","@brave/brave-search-mcp-server"]`, `env: {BRAVE_API_KEY: "..."}`

  * http mode: add `--transport http` or set `BRAVE_MCP_TRANSPORT=http`. ([GitHub][9])
* **duckduckgo (stdio)**
  `command: uvx`, `args: ["duckduckgo-mcp-server"]` (no key). ([GitHub][12])
* **serper (stdio)**
  `command: npx`, `args: ["-y","serper-search-scrape-mcp-server"]`, `env: {SERPER_API_KEY: "..."}`. ([GitHub][13])

> **fetchers**

* **mcp‑server‑fetch (stdio)**
  `command: python`, `args: ["-m","mcp_server_fetch"]` (or `uvx mcp-server-fetch`). ([PyPI][5])
* **scrapling (stdio/http)**
  `command: scrapling`, `args: ["mcp"]` or `["mcp","--http"]`. ([scrapling.readthedocs.io][11])
* **firecrawl (stdio/http)**
  `command: npx`, `args: ["-y","firecrawl-mcp"]`; http: set `HTTP_STREAMABLE_SERVER=true`. ([Firecrawl][10])

> **rag**

* **qdrant (stdio/sse/http)**
  `command: uvx`, `args: ["mcp-server-qdrant"]`, env `QDRANT_URL`, `COLLECTION_NAME`, etc. ([GitHub][14])
* **chroma (stdio/http/cloud)**
  `command: uvx`, `args: ["chroma-mcp","--client-type","persistent","--data-dir","{{CHROMA_DATA_DIR}}"]`. ([GitHub][15])

---

## does any candidate persist catalogs on its own?

* **generally no** — these servers return results or content but don’t manage your “bookmarks.” exceptions are *platform* concepts (e.g., **exa** “websets”), but the mcp page doesn’t expose webset CRUD; use your aggregate’s state file for curated lists + tags. ([docs.exa.ai][8])

---

## how we’d stage the cut‑over

1. **add new aggregate** `documentation_catalog` with the ops above; state at `${STELAE_STATE_HOME}/doc_catalog.json`. the retired `doc_fetch_suite` is gone, so parity tests now run directly against `documentation_catalog` plus the external fetch/search servers.
2. **install** the chosen searcher(s) + fetcher(s) + rag via `manage_stelae`. missing env keys get hydrated into `${STELAE_CONFIG_HOME}/.env.local`.
3. **wire the routes** (search→tavily/exa/brave/ddg; fetch→fetch/scrapling/firecrawl; rag→qdrant/chroma) in the aggregate json; render/restart as usual.
4. **remove the legacy documentation binary** from the starter bundle and delete the repo‑tracked files once parity checks pass (your core template is already designed to keep optional stacks out of git). ⁄(⁄ ⁄•⁄-⁄•⁄ ⁄)⁄

---

## small notes / trade‑offs

* **brave** has top‑tier verticals (news/images/local) and a summarizer, but you still need a fetcher to read pages in full. ([GitHub][9])
* **scrapling** is your “break glass” retriever for cloudflare/turnstile/js‑heavy pages; it’s heavier than `mcp‑server‑fetch` but worth it for the hard cases. ([scrapling.readthedocs.io][11])
* **firecrawl** overlaps with tavily/exa on extract/crawl; pick one to minimize overlap unless you specifically want its site‑map style crawling. ([Firecrawl][10])
* **qdrant vs chroma**: qdrant is a lean vector store with a clean mcp; chroma adds text search + flexible client types (ephemeral/persistent/http/cloud). both slot in behind the same aggregate ops. ([GitHub][14])

---

## tie‑back to stelae’s architecture

* overlays live under `${STELAE_CONFIG_HOME}`; runtime json is emitted into `${STELAE_STATE_HOME}`; pm2 reads only from state—so this replacement keeps your clone‑safe workflow intact.
* `manage_stelae` can discover/install servers and append env placeholders safely, then re‑render + restart; we’ll use the same path for these candidates.

if you want, i can draft the `documentation_catalog` aggregate json (argument/response mappings + state schema) so you can drop it straight into your overlay and test against tavily+fetch (fastest happy‑path), then layer scrapling/qdrant after. ୧| ͡ᵔ ﹏ ͡ᵔ |୨

**sources**
tavily mcp docs (tools + http url) ([GitHub][7]) · exa mcp (remote url, tools, npx) ([docs.exa.ai][8]) · brave search mcp (tools, stdio/http, docker, api key) ([GitHub][9]) · firecrawl mcp (npx, streamable http, search/map/crawl/extract) ([Firecrawl][10]) · scrapling mcp (tools incl. stealthy_fetch; stdio/http; docker) ([scrapling.readthedocs.io][11]) · mcp‑server‑fetch (pip/uvx/docker; proxy; markdown) ([PyPI][5]) · duckduckgo mcp (keyless search + fetch; uv/npx smithery) ([GitHub][12]) · serper mcp (google operators + scrape; npx/docker) ([GitHub][13]) · qdrant mcp (store/find; transports) ([GitHub][14]) · chroma mcp (collection mgmt; embedding providers; persistent/http/cloud) ([GitHub][15])

**stelae refs**
legacy docs stack + aggregates + bundle; state + overlays; render/restart flow.

[1]: https://github.com/tavily-ai/tavily-mcp?utm_source=chatgpt.com "tavily-ai/tavily-mcp: Production ready MCP server with real- ..."
[2]: https://github.com/qdrant/mcp-server-qdrant?utm_source=chatgpt.com "An official Qdrant Model Context Protocol (MCP) server ..."
[3]: https://github.com/chroma-core/chroma-mcp?utm_source=chatgpt.com "chroma-core/chroma-mcp: A Model Context Protocol ( ..."
[4]: https://github.com/brave/brave-search-mcp-server?utm_source=chatgpt.com "Brave Search MCP Server"
[5]: https://pypi.org/project/mcp-server-fetch/?utm_source=chatgpt.com "mcp-server-fetch"
[6]: https://scrapling.readthedocs.io/en/latest/ai/mcp-server/?utm_source=chatgpt.com "AI MCP server - Scrapling"
[7]: https://github.com/tavily-ai/tavily-mcp "GitHub - tavily-ai/tavily-mcp: Production ready MCP server with real-time search, extract, map & crawl."
[8]: https://docs.exa.ai/reference/exa-mcp "Exa MCP - Exa"
[9]: https://github.com/brave/brave-search-mcp-server "GitHub - brave/brave-search-mcp-server"
[10]: https://docs.firecrawl.dev/mcp-server?utm_source=chatgpt.com "Firecrawl MCP Server"
[11]: https://scrapling.readthedocs.io/en/latest/ai/mcp-server/ "AI MCP server - Scrapling"
[12]: https://github.com/nickclyde/duckduckgo-mcp-server "GitHub - nickclyde/duckduckgo-mcp-server: A Model Context Protocol (MCP) server that provides web search capabilities through DuckDuckGo, with additional features for content fetching and parsing."
[13]: https://github.com/marcopesani/mcp-server-serper "GitHub - marcopesani/mcp-server-serper: Serper MCP Server supporting search and webpage scraping"
[14]: https://github.com/qdrant/mcp-server-qdrant "GitHub - qdrant/mcp-server-qdrant: An official Qdrant Model Context Protocol (MCP) server implementation"
[15]: https://github.com/chroma-core/chroma-mcp "GitHub - chroma-core/chroma-mcp: A Model Context Protocol (MCP) server implementation that provides database capabilities for Chroma"
