# Stelae MCP: Clone Smoke Test Recovery, Catalog Hygiene, and Doc Consolidation — gpt-5-high Assessment (2025-11-13)

## 1. Executive Summary

- The core vs optional stack split is now correct and enforced. Optional servers (Docy, filesystem, rg, terminal, memory, Strata, Scrapling, wrapper) are installed into `${STELAE_CONFIG_HOME}` overlays via the starter bundle; tracked templates keep only self-management and the aggregator helper.
- A key improvement landed: clear separation between default and local tool aggregations and their effects on tool overrides, preventing catalog contamination and duplicate schema array members. The exporter dedupes JSON Schema `enum`/`required` arrays.
- The streamable bridge now executes `manage_stelae` locally, so install/remove operations complete even while the Go proxy restarts—fixing prior mid-call disconnects.
- The clone smoke harness matured: randomized `PROXY_PORT`, isolated PM2/CODEX homes, JSONL transcript parsing, staged automation/manual flows, and structural repo cleanliness checks.
- Regressions were caused by (a) mixing default and local aggregations into runtime overrides and (b) expecting the proxy to stay up during restart-heavy flows; both are addressed. Remaining friction is around occasional pm2 `EPIPE`/readiness flakiness; recommended mitigations are proposed.

## 2. Scope and Inputs

Read and analyzed:

- README.md, docs/ARCHITECTURE.md, docs/e2e_clone_smoke_test.md
- Recent task notes: dev/tasks/codex-manage-stelae-smoke.md, dev/tasks/e2e-clone-smoke-test.md, dev/tasks/clone-smoke-harness-stability.md, dev/tasks/stelae-tool-aggregation-visibility.md, dev/tasks/stelae-mcp-catalog-consistency.md
- Recent commits and diffs (~last 17), with particular attention to:
  - scripts/stelae_streamable_mcp.py
  - scripts/process_tool_aggregations.py, scripts/tool_aggregator_server.py
  - stelae_lib/integrator/tool_aggregations.py, stelae_lib/integrator/tool_overrides.py, stelae_lib/integrator/core.py
  - scripts/run_e2e_clone_smoke_test.py, stelae_lib/smoke_harness.py
  - scripts/restart_stelae.sh, scripts/render_proxy_config.py, ecosystem.config.js
  - config/proxy.template.json, config/tool_aggregations.json, config/tool_overrides.json
  - tests/test_repo_sanitized.py

## 3. Architecture Snapshot (ground truth)

- Templates vs overlays: tracked configs under `config/` are rendered with `.env` + `${STELAE_CONFIG_HOME}/.env.local`. Runtime artifacts (proxy.json, tool_overrides.json, discovery cache, schema status, cloudflared config) live under `${STELAE_CONFIG_HOME}` and never in git.
- Core vs optional: core templates declare only self-management servers (`custom`, `integrator`, `one_mcp`, `public_mcp_catalog`, `tool_aggregator`). Optional bundle lives in `config/bundles/starter_bundle.json` and installs into overlays only.
- Aggregations: `config/tool_aggregations.json` holds only in-repo aggregation defaults (`manage_docy_sources`); optional/local aggregations go to `${STELAE_CONFIG_HOME}/tool_aggregations.local.json`. Exporter writes only the relevant layer (`--scope default` vs `--scope local`) and dedupes JSON Schema arrays before emitting runtime overrides.
- Streamable bridge: `scripts/stelae_streamable_mcp.py` exposes a connector-friendly MCP server. It proxies most tools to the Go proxy but directly dispatches `manage_stelae` to the local `StelaeIntegratorService`, making install/remove robust across proxy restarts.
- Restart orchestration: `scripts/restart_stelae.sh` builds the Go proxy, ensures pm2 apps, waits on the randomized `PROXY_PORT`, probes readiness via HTTP JSON-RPC, populates overrides via the proxy catalog, and only then starts cloudflared.

## 4. Recent Improvements (with evidence)

- Aggregation hygiene and separation
  - Added `--scope local|default` to `scripts/process_tool_aggregations.py` so overlays and defaults are processed independently; default scope is `local` for runtime.
  - `ToolOverridesStore._merged_payload()` now calls `_dedupe_schema_arrays()` to canonicalize JSON Schema arrays; repeated renders or overlay edits no longer corrupt manifests.
  - Tests: `tests/test_repo_sanitized.py` enforces core-only servers in tracked templates and presence of only `manage_docy_sources` in tracked aggregation defaults.

- Streamable bridge stability
  - `scripts/stelae_streamable_mcp.py` routes `manage_stelae` calls to `_run_manage_operation` using `StelaeIntegratorService` locally; adds robust debug logging (`STELAE_STREAMABLE_DEBUG_*`) and safer JSON response handling for proxy errors.

- Restart and render consistency
  - `config/proxy.template.json` renders `addr: :{{PROXY_PORT}}` from layered envs; the smoke harness explicitly sets `PROXY_PORT`, `PUBLIC_PORT`, and `PUBLIC_BASE_URL` to a randomized port, avoiding conflicts.
  - `scripts/restart_stelae.sh` waits for the port, performs local probes, then populates overrides via proxy `tools/list` using the `x-stelae.servers` metadata to map schemas correctly.

- Smoke harness maturation
  - `scripts/run_e2e_clone_smoke_test.py` creates a disposable workspace, mirrors `.codex`, randomizes port, installs the starter bundle with `--no-restart`, restarts stack with logs, runs staged Codex missions (`--json`), parses transcripts for expected tool calls, and asserts clean git state. Supports `--manual` and `--manual-stage` gates for human-driven steps.

## 5. Regressions and Root Causes

- Catalog contamination (fixed): optional/local aggregations were being reflected into tracked or runtime overrides broadly, and merging overlays twice produced duplicate `enum`/`required` array items. Fixes: restrict export scope to the intended layer, dedupe at export time, and keep tracked defaults minimal. Tests lock this in.
- Mid-call disconnect on restart (fixed): Codex calls to `manage_stelae` dropped when the proxy restarted. Fix: streamable bridge handles `manage_stelae` locally so calls survive proxy churn.
- Harness stalls and pm2 `EPIPE` (mitigated): stalls occurred when proxy bound to a conflicting port or pm2 encountered pipe errors during rapid restarts. Mitigations now include: randomized port, explicit kill of stray listeners on the target port, improved logs/timeouts, and clearer guidance that “timeouts imply orchestration issues, not slowness.” Recommendation below strengthens readiness behavior further.

## 6. Current Status

- Core stack renders and restarts cleanly; local probes show a reasonable tool count and correct aggregate exposure.
- `workspace_fs_read`, `grep`, `doc_fetch_suite`, and `manage_stelae` are available in recent harness runs; docs note that Docy may return an empty source list by default, which should be interpreted as “tool available; dataset empty”.
- Clone smoke harness still has occasional environmental stalls; logs and parameterization help, but adding bounded backoffs and reducing dependence on pm2 state during initial readiness would improve reliability.

## 7. Recommendations and Next Actions

A. Consolidate task docs into a staged roadmap

- Stage 1 – Catalog Consistency & Aggregations
  - Ensure only aggregates appear in `tools/list` and schemas are deduped; lock behavior with a manifest snapshot test in the sandbox (no network).
- Stage 2 – Clone Smoke Harness Reliability
  - Add bounded readiness backoff (HTTP JSON-RPC `initialize` + `tools/list` with retry and small delays) before proceeding to `populate_tool_overrides`.
  - Harden pm2 interactions: on `EPIPE`, backoff and re-ensure app instead of failing the entire run immediately.
- Stage 3 – Restart/Manage Semantics
  - Keep the streamable bridge handling for `manage_stelae`; document this invariant in ARCHITECTURE.md.
  - Optional: add a “restart-and-wait” MCP operation within `manage_stelae` that reports progress and reconnects.
- Stage 4 – Docs Unification
  - Merge scattered task notes into a single `dev/tasks/roadmap.md` that links to focused appendices where needed.

B. Doc information architecture (IA) updates

- README.md
  - Quick Start: clone → `.env` → `make render-proxy` → install starter bundle (overlays only) → `make up` / restart.
  - Optional Bundle: clear that it writes to `${STELAE_CONFIG_HOME}` only; how to remove via `.local` cleanup.
  - Troubleshooting: “if it takes >60s at ‘Installing…’ or ‘Restarting…’, it’s orchestration—check env/pm2 and logs; do not raise timeouts.”
- docs/ARCHITECTURE.md
  - One diagram: Template → Overlay → Runtime; where each artifact lives.
  - Aggregations: default vs local scopes and dedupe pass; how the aggregator server reads the merged config.
  - Streamable bridge: why `manage_stelae` is local and how restart-safe calls work.
- docs/e2e_clone_smoke_test.md
  - Single authoritative CLI invocation, time budgets, success criteria (minimum tool calls), and manual-stage usage.

C. Harness hardening (surgical)

- Add JSON-RPC readiness checker with 3–5 short retries (e.g., 500ms → 2s) before `populate_overrides_via_proxy`.
- If pm2 reports `EPIPE`, re-run `pm2 start …` for the specific app with a short delay.
- Add a minimal manifest sanity test when running in a sandbox context: ensure no duplicate schema array members and only aggregates are enabled.

D. Guardrails and CI

- Keep `tests/test_repo_sanitized.py` as the tracked-template gate; add one lightweight test to validate the rendered runtime manifest in a hermetic mode (no network) when TOX/CI signals a sandbox.
- Optionally schedule a nightly clone harness run (manual for now) and archive logs under `logs/codex-transcripts/`.

## 8. Short-Term Action Plan (2–4 hours)

1) Readiness backoff in restart script and harness
    - Add retry loop around the first JSON-RPC call (`initialize` then `tools/list`) with bounded backoff before running `populate_overrides_via_proxy`.
    - Surface a precise error message when the proxy returns non-JSON; streamable bridge already includes a safe decoder.
2) Consolidated task file stub
    - Create `dev/tasks/roadmap.md` with the four stages above; link existing task docs as references.
3) Docs touch-ups
    - README.md: add Troubleshooting subsection and refresh Optional Bundle wording.
    - ARCHITECTURE.md: add the “Streamable `manage_stelae`” invariant and the default vs local aggregation scopes.
4) Sanity manifest check
    - Add a small test function that loads `${STELAE_CONFIG_HOME}/tool_overrides.json` when present and asserts no duplicate `enum`/`required` members and that expected aggregates are present.

## 9. Risks and Open Questions

- Docy catalog baseline: Should we ship a minimal enabled source set in the starter bundle overlay to make `doc_fetch_suite` look less “empty” in smoke runs? Current behavior is correct but can mislead testers.
- Discovery descriptors: The 1mcp metadata hydration now filled gaps for qdrant; decide which servers we officially support in discovery and document the required env defaults.
- Public catalog bridge: Ensure rate limiting and error handling remain friendly when remote `public_mcp_catalog` flaps; consider a quick readiness gate before advertising it.

## 10. Operational Notes & Commands

- Verify local manifest tools quickly:

  ```bash
  curl -s http://127.0.0.1:$PROXY_PORT/mcp -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' | jq '{count: (.result.tools|length), names: (.result.tools|map(.name)[0:15])}'
  ```

- Streamable bridge debugging:
  - `STELAE_STREAMABLE_DEBUG_TOOLS="*,manage_stelae" STELAE_STREAMABLE_DEBUG_LOG=~/.config/stelae/streamable_tool_debug.log`
- Aggregator debugging:
  - `STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS="manage_docy_sources" STELAE_TOOL_AGGREGATOR_DEBUG_LOG=~/.config/stelae/agg_debug.log`
- Restart quickly without CF/bridge:

  ```bash
  scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared
  ```

## 11. Evidence Map (selected)

- Aggregation separation and dedupe: `scripts/process_tool_aggregations.py`, `stelae_lib/integrator/tool_overrides.py`, `stelae_lib/integrator/tool_aggregations.py`.
- Streamable `manage_stelae` handling and debug: `scripts/stelae_streamable_mcp.py`.
- Restart behavior: `scripts/restart_stelae.sh`, `config/proxy.template.json`, `scripts/render_proxy_config.py`.
- Harness: `scripts/run_e2e_clone_smoke_test.py`, `stelae_lib/smoke_harness.py`.
- Template guardrails: `tests/test_repo_sanitized.py`.
