# Stelae MCP: Clone Smoke Test Recovery, Catalog Hygiene, and Doc Consolidation — Codex Synth Assessment (2025-11-13)

## Executive Summary

- Core vs optional stack boundaries are now codified in `README.md` (Core vs Optional Stack, Declarative Tool Aggregations) and `docs/ARCHITECTURE.md` (Config overlays, Core vs optional bundle). Optional servers and aggregations live exclusively under `${STELAE_CONFIG_HOME}` overlays, keeping tracked templates clean while allowing the starter bundle to expose filesystem/ripgrep/Docy tooling on demand.
- Tool aggregation/export fixes (`scripts/process_tool_aggregations.py`, `stelae_lib/integrator/tool_overrides.py`) eliminate duplicate JSON Schema enums/required sets and prevent local overlays from leaking back into tracked defaults. `tests/test_repo_sanitized.py` plus new aggregation tests enforce this hygiene.
- The FastMCP bridge now handles `manage_stelae` locally (`scripts/stelae_streamable_mcp.py`), so install/remove operations survive Go proxy restarts. Fresh debug knobs (`STELAE_STREAMABLE_DEBUG_*`, `STELAE_TOOL_AGGREGATOR_DEBUG_*`) record raw payloads when Codex encounters parse errors.
- The Codex-driven clone smoke harness (`scripts/run_e2e_clone_smoke_test.py`, `docs/e2e_clone_smoke_test.md`) provisions isolated workspaces, mirrors `.codex`, randomizes `PROXY_PORT`, stages pytest/`make verify-clean`, and captures JSONL transcripts for `bundle-tools`, `install`, and `remove` scenarios.
- Remaining risks center on Codex still seeing `Expecting value` from `workspace_fs_read`, restarts that time out even at 1200 s when pm2 collides with the dev stack, and fragmented task docs that obscure owners/priorities.

## Timeline Snapshot (Nov 10–13)

1. **fd0aa59 infra: add e2e clone smoke test harness** — introduced `scripts/run_e2e_clone_smoke_test.py`, sandbox `.env` handling, and docs baseline.
2. **15683c3 / 6c5629a** — hardened automation (pytest bootstrap inside sandbox, JSONL transcript parsing, Codex prompt scaffolding, manual stages).
3. **9d2d888 / 64bfb0f / 4066ccc / 9f97ea1** — documented restart stalls caused by pm2 binding to the developer’s `:9090`, added randomized ports, but noted readiness still blocks (`dev/tasks/clone-smoke-harness-stability.md`).
4. **a46a1ed project: enforce core tool aggregation defaults** — split default/local aggregation scopes, deduped schemas, added tests (`tests/test_tool_aggregations.py`).
5. **4b01248 project: stelae mcp catalog fix** — taught FastMCP to pass downstream payloads verbatim via `PassthroughFuncMetadata`, mitigating aggregator schema mismatches and enabling new debug envs.

## What’s Working

- **Catalog hygiene:** Only `manage_docy_sources` ships in tracked aggregations, and `scripts/process_tool_aggregations.py --scope local` writes starter-bundle composites to `${STELAE_CONFIG_HOME}` before renders, keeping manifests minimal by default.
- **Restart flow:** `scripts/run_restart_stelae.sh` now waits on the randomized port, probes `/mcp`, and logs `pm2 ensure <app>` transitions so the harness can see when the proxy/bridge/tunnel recover.
- **Smoke harness artifacts:** Disposable `${STELAE_CONFIG_HOME}`, pm2 home, `codex-transcripts/*.jsonl`, and manual playbooks capture each stage. Harness asserts `workspace_fs_read`, `doc_fetch_suite`, `grep`, and `manage_stelae` calls appear before completing, doubling as catalog verification.
- **Instrumentation:** `STELAE_STREAMABLE_DEBUG_TOOLS` + `STELAE_STREAMABLE_DEBUG_LOG` (bridge) and `STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS` + `STELAE_TOOL_AGGREGATOR_DEBUG_LOG` (aggregator) now dump request/response JSON, providing the evidence needed to resolve Codex parsing failures.

## Active Regressions / Risks

1. **Codex JSON parsing failures:** `workspace_fs_read` still intermittently returns `Expecting value` inside Codex despite successful HTTP tests (`dev/tasks/stelae-mcp-catalog-consistency.md`). Hypothesis: FastMCP or the aggregator is double-encoding payloads or streaming partial chunks. No end-to-end log yet captures what Codex actually received.
2. **Harness restart brittleness:** Even with randomized ports and isolated pm2 homes, `scripts/run_restart_stelae.sh` can consume the full stage timeout when readiness probes never flip (e.g., pm2 `EPIPE`, lingering sockets, proxy health check blocking). When this happens the Codex stages never run, but the harness simply reports a timeout without artifacts.
3. **Doc/task fragmentation:** At least five overlapping task files (`dev/tasks/e2e-clone-smoke-test.md`, `clone-smoke-harness-stability.md`, `stelae-tool-aggregation-visibility.md`, `stelae-mcp-catalog-consistency.md`, `codex-manage-stelae-smoke.md`) plus `docs/e2e_clone_smoke_test.md` cover the same initiative, making it hard to see blockers, owners, or completion criteria.
4. **Operator guidance gaps:** README and ARCHITECTURE describe overlays conceptually but stop short of a prescriptive “after editing defaults run: `process_tool_aggregations.py --scope default`, `process_tool_aggregations.py --scope local`, `make render-proxy`, `pytest tests/test_repo_sanitized.py`.” This absence led to earlier contamination and will regress without an explicit checklist.

## Action Plan

### 1. Close the Codex parsing loop

- [x] **Preread:** `README.md` (Core vs Optional Stack, Declarative Tool Aggregations), `docs/ARCHITECTURE.md` (Config overlays, Discovery & auto-loading pipeline), `docs/e2e_clone_smoke_test.md` (Automated harness + Artifacts), `dev/tasks/stelae-mcp-catalog-consistency.md` (latest failures).
- [x] Enable `STELAE_STREAMABLE_DEBUG_TOOLS="workspace_fs_read,doc_fetch_suite"` and `STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS="workspace_fs_read"` inside the harness; persist logs under `${WORKSPACE}/logs/` for each stage. _Harness now exports these variables automatically when the new flag (below) is set and writes the live files to `${WORKSPACE}/logs/streamable_tool_debug.log` / `tool_aggregator_debug.log`._
- [x] Add a harness flag (`--capture-debug-tools`) that automatically sets these env vars and copies the resulting logs into `codex-transcripts/`. _Added `--capture-debug-tools`, which enables the env vars, rolls stage-specific log copies (`<stage>-*.log`) into both `${WORKSPACE}/logs/` and `codex-transcripts/`, and resets the live logs between stages._
- [x] Mirror the resulting `streamable_tool_debug.log` (and related aggregator snapshots) into `dev/logs/harness/<timestamp>-streamable-tool-debug.log` while the run is active so artifacts survive when the workspace is deleted. _Each stage now mirrors its snapshot into `dev/logs/harness/<run-timestamp>-<stage>-*.log`, guaranteeing evidence persists after workspace cleanup._
- [x] Create a focused pytest (`tests/test_streamable_mcp.py::test_workspace_fs_read_roundtrip`) that launches `scripts/stelae_streamable_mcp.py` against a stub server to verify the JSON envelope Codex expects. _`test_workspace_fs_read_roundtrip` now stubs the proxy RPC, asserts the aggregator inputs, and validates the text block + `structuredContent` encoding returned to Codex._

### 2. Harden restart/readiness

- [x] **Preread:** `README.md` (Runtime, Build, and Dev Commands → PM2 lifecycle), `docs/ARCHITECTURE.md` (Component Topology, Operational Notes), `docs/e2e_clone_smoke_test.md` (Prerequisites + Restart flow), `dev/tasks/clone-smoke-harness-stability.md` (timeout timeline). _Captured the exact readiness contract (pm2 ensure + `/mcp` probe expectations) and the documented timeout ceiling (≤120 s) so the new instrumentation mirrors the published operator guidance._
- [x] Wrap the proxy JSON-RPC probe in a short backoff loop (e.g., 0.5s/1s/2s/4s) and fail fast with a structured error that includes the target port and last HTTP response. _`scripts/restart_stelae.sh` now calls `probe_jsonrpc_initialize`, which retries the `initialize` RPC with 0/0.5/1/2/4 s spacing, logs the successful payload, and dumps the final HTTP status + truncated body before exiting if all attempts fail (lines 120–170 & 360)._
- [x] Teach `scripts/run_e2e_clone_smoke_test.py` to surface pm2 stdout/stderr snippets when `run_restart_stelae.sh` exceeds its timeout, and optionally retry restarts once before abandoning the stage. _CloneSmokeHarness gained `--restart-timeout/--restart-retries`, per-attempt timers around the restart script, automatic pm2 status dumps, and tail-of-log snippets from `${PM2_HOME}/logs/*` whenever the timeout triggers (see `_run_restart_with_retry` and `_collect_restart_diagnostics`)._
- [x] Add a lightweight “port preflight” that kills lingering listeners on the randomized `PROXY_PORT` before pm2 starts, preventing silent binds to the developer’s existing proxy. _Before invoking the restart helper the harness now inspects `ss`/`lsof`, force-kills any listeners on the chosen port (using SIGKILL/SIGTERM fallback), and re-verifies the port is clear so pm2 doesn’t collide with leftover proxy instances._
- [x] Ensure the harness exits instead of hanging indefinitely when downstream tools wedge. _A background heartbeat monitor (default 240 s, configurable via `--heartbeat-timeout`) now tracks log activity; if no new output arrives within the window it logs the timeout reason and sends `SIGTERM` to itself so agents aren’t left waiting forever._

### 3. Consolidate documentation/work tracking

- [ ] **Preread:** `README.md` (Core vs Optional Stack, Declarative Tool Aggregations), `docs/ARCHITECTURE.md` (Config overlays), all existing task docs listed in Active Risks #3, plus `docs/e2e_clone_smoke_test.md` (Manual stages).
- [ ] Merge the existing task docs into `dev/tasks/stelae-smoke-readiness.md` with three sections: (a) Catalog hygiene, (b) Harness + restart reliability, (c) Codex orchestration. Keep dated appendices for historical run logs; link this doc from `dev/progress.md` and `docs/e2e_clone_smoke_test.md`. _Still pending; no consolidation yet._
- [ ] Expand README and ARCHITECTURE with an “Overlay workflow & guardrails” subsection that spells out the renderer/pytest loop and explicitly points to the starter bundle installer for aggregates. _Still pending; recent changes focused on harness instrumentation._
- [ ] Update `docs/e2e_clone_smoke_test.md` to emphasize that long pauses at “Installing starter bundle…” or “Restarting stack…” indicate orchestration failures, not intended waits. _Partially addressed: the doc now documents `--capture-debug-tools`, the resulting artifacts, and reiterates that long stalls indicate orchestration failures; it now also needs to mention the `--restart-timeout/--restart-retries/--heartbeat-timeout` knobs, the pm2-diag log tails, and the automatic port-preflight expectations so operators know what to look for._

### 4. Bake guardrails into automation

- [ ] **Preread:** `README.md` (Troubleshooting), `docs/ARCHITECTURE.md` (Catalog Aggregation & Overrides), `tests/test_repo_sanitized.py`, and `docs/e2e_clone_smoke_test.md` (Validation + Feedback).
- [ ] Extend `tests/test_repo_sanitized.py` (or add a sibling test) to load a rendered manifest sample and assert aggregate names + schema dedupe, preventing regressions before manual harness runs. _Not started; the new FastMCP round-trip test only covers `workspace_fs_read` serialization. The restart harness now enforces JSON-RPC backoff + port preflight, so a follow-on test should also cover the `probe_jsonrpc_initialize` path (e.g., simulate a failure and assert the structured error text) once manifests are exercised, and a watchdog-focused test should verify the heartbeat timeout emits SIGTERM as expected._
- [ ] Consider adding a nightly clone-harness run (manual or shepherded by CI) that archives `codex-transcripts` and `logs/streamable_tool_debug.log` as artifacts, so regressions are caught before release crunches. _Still pending, though the per-stage log mirroring implemented above will make artifact capture trivial once scheduling begins._

## Key References

- `README.md` — Core vs Optional Stack, Declarative Tool Aggregations, Docy source catalog, declarative tool aggregations, Troubleshooting.
- `docs/ARCHITECTURE.md` — Config overlays, Component topology, Discovery & auto-loading pipeline.
- `docs/e2e_clone_smoke_test.md` — Harness prerequisites, staged automation/manual flows, artifact layout.
- `scripts/run_e2e_clone_smoke_test.py`, `stelae_lib/smoke_harness.py` — automation entry point and helper library.
- `scripts/stelae_streamable_mcp.py`, `stelae_lib/integrator/tool_aggregations.py` — FastMCP bridge routing + aggregation runtime.
