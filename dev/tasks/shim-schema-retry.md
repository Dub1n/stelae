# Task: Shim schema-aware retry ladder

Related requirement: `dev/progress.md` → Requirement Group A → "Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides (with guardrails)."

Tags: `#infra`

Prerequisite: `dev/tasks/tool-override-population.md`

## Checklist

- [x] Teach the shim to read each tool's declared `outputSchema` from `config/tool_overrides.json` before executing a tool.
- [x] Implement retry ladder: pass-through → wrap according to declared schema → generic wrapper → bubble error.
- [x] Ensure fallback annotations/logging capture which step produced the final response.
- [x] Update docs (`README.md`, `docs/ARCHITECTURE.md`, relevant task notes) to describe the new order of operations.
- [x] Update `dev/progress.md` / task references.
- [x] Commit with message `infra: add schema-aware shim retry` after tests.

## References

- Code: `scripts/stelae_streamable_mcp.py`, `config/tool_overrides.json`, `config/tool_schema_status.json`
- Tests: `tests/test_streamable_bridge_manage_tool.py` (local bridge fallbacks) plus Go proxy adapter unit tests in `~/apps/mcp-proxy`.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `dev/tasks/tool-override-population.md`

## Notes

- Requires populated overrides (see prerequisite task) so the shim has a baseline schema to compare against.
- Consider surfacing telemetry (e.g., logs or status file note) so we can audit how often each step is used.
- Delivered via `scripts/mcp_output_shim.py` (declared-schema wrapper before generic fallback) and documented in README/architecture notes.

---

## Current Status (2025-11-07)

- Override expansion (Go proxy) merged; schemas are overridable and flow to manifest/tools.list.
- Shim generalized with retry ladder: pass-through → declared-schema wrap → generic `{result: ...}`.
- Override auto-population helper added to pre-fill missing schemas from downstream servers.
- Unit tests pass for shim helpers and override population store.

### Smoke Testing Summary

- Direct Scrapling (no shim): ok. `uvx scrapling-fetch-mcp --stdio` lists `s_fetch_page`, `s_fetch_pattern`.
- Shim as a server: starting `python3 scripts/mcp_output_shim.py` and calling `list_tools` hangs after the shim logs "Processing request of type ListToolsRequest".
- CLI “stelae” tool path (non-proxy): `stelae.s_fetch_page(https://example.com)` returns METADATA+body text successfully (acceptable for this path; it bypasses proxy validation).
- Proxy + shim path: after wiring env into proxy template and restarting, `/mcp` tools.list does not include `s_fetch_*` yet, so Scrapling is not registering under the proxy.

### Config State During Test

- Cleared scrapling tool schemas in `config/tool_overrides.json` and reset `config/tool_schema_status.json` to `{}` for scrapling to exercise auto-classification. After restart + local call, files remained unchanged (expected since the local call did not traverse the proxy+shim validator).

### Hypothesis

- Child process launched by the shim (`uvx scrapling-fetch-mcp --stdio`) is not completing its handshake when spawned by our process. Likely environment mismatch under pm2 (e.g., missing PLAYWRIGHT_BROWSERS_PATH or PATH to uvx). Less likely: stdout noise interfering with stdio.

### Next Steps

1) Ensure shim child env via proxy template: set PLAYWRIGHT_BROWSERS_PATH (default ~/.cache/ms-playwright) and, if needed, extend PATH for uvx.
2) Add shim diagnostics (log child command/env, add timeouts + single retry around initialize/list_tools).
3) Re-verify proxy path: tools.list should include s_fetch_*; first call should write state (wrapped) and outputSchema back to config files.
4) Contingency: temporarily point `scrapling` directly at `uvx scrapling-fetch-mcp --stdio` in the proxy to confirm catalog registration, then restore shim after env fixes.

### Status

- Paused with shim-child not registering under proxy. Local non-proxy calls work. Resume by hardening env + adding diagnostics to complete proxy-path verification and auto write-back.

---

## Direction Change: Centralize Adapter in Go Proxy (2025-11-07)

Decision: migrate the schema-aware retry logic from the Python shim to the Go proxy so adaptation applies to any server/transport without introducing per-server launch shims. The proxy remains the single aggregation point; we stop running Scrapling through a Python wrapper once the proxy adapter is in place.

### Implementation status (2025-11-10)

- ✅ `config/proxy.template.json:22` now passes `toolSchemaStatusPath` to the Go proxy so call-path adapters can persist telemetry. `config/tool_schema_status.json` is actively updated at runtime (see the `integrator`, `scrapling`, and `strata` entries committed to git).
- ✅ The shim retry ladder lives inside the proxy; Scrapling is wired directly to `uvx scrapling-fetch-mcp --stdio` while still benefitting from automatic schema enforcement (documented in README.md:21 and reflected in the Scrapling pass-through entries inside `config/tool_schema_status.json:33-46`).
- ✅ `scripts/mcp_output_shim.py` has been removed entirely (along with its unit tests); the Go adapter plus overrides cover every server, so there is no longer a second shim entry point to maintain.
- 🔴 No additional cleanup required beyond monitoring adapter telemetry.

Key points

- Catalog behavior unchanged: the proxy already applies `config/tool_overrides.json` to manifests and tools.list. We do not modify merge rules or surface/visibility semantics. Invalid/missing overrides should log warnings but never hide tools.
- Adapter chain moves to call path inside the proxy and updates overrides based on successful adaptation, so the next restart reflects correct `outputSchema` in manifests/tools.list.
- Works for stdio and HTTP servers because adaptation occurs after transport responses are decoded.

Adapter Chain (proxy, call path)

- Pass-through: if the server returns `structuredContent` (object), return as-is; do not modify overrides.
- Declared wrap: use `servers[server].tools[tool].outputSchema` from overrides to adapt plain string results. If the declared schema implies a safe mapping (e.g., exactly one required string field), wrap into that field. If the declared schema expects a richer shape (e.g., `{metadata, content}`), apply narrow heuristics inline (e.g., handle `METADATA: {json}\n\n<body>` when present) without introducing an extra stage.
- Generic wrap: final fallback to `{ result: "..." }` for plain strings when declared mapping cannot be satisfied.
- On successful adaptation, record `outputSchema` to overrides if not already equal; emit a log hint to re-render; optional auto-write flag is acceptable.

Persistence Rules (Overrides + Status Store)

- Overrides source of truth: `config/tool_overrides.json` continues to drive manifests/tools.list; the adapter may update it atomically when adaptation succeeds.
- Promote generic when used:
  - If no declared `outputSchema` exists for a tool, persist the generic `{result: string}` schema on the first successful generic adaptation.
  - If a declared schema exists but adaptation fails, fall back to generic for that call and increment a per-tool counter in `config/tool_schema_status.json` (`consecutive_generic_count`). After a small threshold (e.g., 2), persist the generic schema to overrides.
- Upgrade later when possible:
  - If a subsequent call succeeds with declared/pass-through adaptation, reset the counter and optionally replace a previously persisted generic override with the declared schema.
- Status store: keep a lightweight runtime file at `config/tool_schema_status.json` with fields at least: `last_adapter` (pass_through|declared|generic), `consecutive_generic_count`, `updated_at`.

Template/config alignment

- Add `"toolSchemaStatusPath": "{{STELAE_DIR}}/config/tool_schema_status.json"` under `manifest` in `config/proxy.template.json` so the proxy knows where to persist status data.
- Scrapling runs direct (no shim) in `mcpServers.scrapling` with `uvx scrapling-fetch-mcp --stdio`.
- The Python shim remains only as a development artifact until proxy adapter lands; do not route through it in production.

Operational timeouts

- Apply a 30s timeout to per-call adaptation (proxy tooling) to avoid hangs; treat timeouts as ordinary call failures without impacting catalog.

Scope & Non-Goals

- No changes to list aggregation semantics. The proxy continues to read overrides at startup and present them in manifest/tools.list. Only the override file is updated opportunistically by the call-path adapter.
- Do not introduce a global shim layer in front of the proxy; reduce process sprawl.

Implementation Plan (companion repo: `~/apps/mcp-proxy`)

- config.go
  - Ensure `ManifestConfig.ToolOverridesPath` parsed; invalid JSON treated as no-op with warning.
  - Add adapter toggles/timeouts: `AdaptToolsEnabled` (default true), `ToolCallTimeout`.
- http.go
  - Call-path adaptation with the 4-step chain above.
  - When adaptation selects a schema different from overrides, write it back (atomically) and log guidance to re-render/restart.
  - Keep list/manifests as-is (read-time overrides only); per-server list timeouts should already exist—validate, don’t change.
- Optional package `adapter/`
  - Encapsulate chain + unit tests, include Scrapling parser.

Migration in this repo (Stelae)

- Short term (until proxy lands): keep hardened Python shim to avoid catalog stalls while testing (timeouts + diagnostics already in place).
- After proxy adapter merges:
  - Point `mcpServers.scrapling` directly to `uvx scrapling-fetch-mcp` (remove Python shim runner).
  - Retain `scripts/populate_tool_overrides.py` for priming; no change to manifest renderer.
  - Remove/deprecate `scripts/mcp_output_shim.py` and related status files after confidence period. *(Done – shim + tests deleted, docs updated to reference the Go adapter instead.)*

Acceptance Criteria

- tools/list shows Scrapling tools regardless of override presence/validity; bad overrides only warn.
- tools/call for string-returning servers returns structuredContent via adapter without upstream changes.
- Successful adapted calls update `config/tool_overrides.json` so after restart the catalog advertises the correct `outputSchema`.
- HTTP and stdio servers both benefit (transport-agnostic handling).

Verification

- Local: `make render-proxy && scripts/run_restart_stelae.sh --full`; confirm `s_fetch_*` in tools.list; call `s_fetch_page` returns `{metadata, content}` structured payload.
- Override write-back: call Scrapling tool once; check `config/tool_overrides.json` updated; tools.list/manifest reflect schema after restart.
- Negative path: corrupt overrides file → logs warning, tools remain listed, calls still adapt.

Risks & Mitigations

- Adapter regressions across heterogeneous servers → isolate logic in adapter package with focused tests; feature flag to disable.
- Override churn/noise → only write on schema change; make auto-write optional via flag.

Rollback

- If proxy adapter causes issues, disable via config flag and temporarily reinstate the Python shim for Scrapling only (existing code kept until confidence reached).
