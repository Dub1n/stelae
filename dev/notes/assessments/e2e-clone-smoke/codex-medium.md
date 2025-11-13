# Stelae MCP: Clone Smoke Test Recovery, Catalog Hygiene, and Doc Consolidation — codex-medium Assessment (2025-11-13)

## Context snapshot

- The README and architecture doc now codify the split between the tracked "core" template and the optional starter bundle, with overlays landing exclusively under `${STELAE_CONFIG_HOME}` so tracked manifests only expose the self-management essentials (README.md §§Core vs Optional Stack & Declarative Tool Aggregations).
- The clone smoke harness (`scripts/run_e2e_clone_smoke_test.py`) is the release gate: it clones into a sandbox, provisions an isolated pm2 home, runs staged pytest/`make verify-clean`, and drives Codex via `codex exec --json --full-auto` across bundle/install/remove stages while asserting transcripts include `workspace_fs_read`, `doc_fetch_suite`, and `manage_stelae` calls (docs/e2e_clone_smoke_test.md §§Automated harness & Key artifacts).
- Recent regressions (duplicate schemas, pm2 restarts colliding with :9090, Codex failures) originated while iterating on that harness and the catalog dedupe work (`dev/tasks/clone-smoke-harness-stability.md`, `dev/tasks/stelae-tool-aggregation-visibility.md`, `dev/tasks/stelae-mcp-catalog-consistency.md`).

## Timeline + state of play

1. **Harness destabilization (Feb–Nov 2025).** Successive harness runs stalled at restart (`timeout … run_e2e_clone_smoke_test.py --manual-stage install`), first because pm2 continued binding :9090 instead of the randomized sandbox port, later because restart health checks never saw `/mcp` ready even though pm2 logged all downstream MCPs (dev/tasks/clone-smoke-harness-stability.md lines 43-151). Subsequent fixes moved `.env`/proxy template handling into the sandbox and warmed pm2 homes, but Codex stages still time out >5 min before producing transcripts (same doc lines 212-219).
2. **Catalog regressions (Nov 2025).** Deduplication of tool aggregations resolved Codex schema rejections, but Codex agents still intermittently fail at `workspace_fs_read` with `Expecting value…` even as raw HTTP calls succeed; new debug hooks in `scripts/stelae_streamable_mcp.py` (`STELAE_STREAMABLE_DEBUG_*` flags) and `stelae_lib/integrator/tool_aggregations.py` (`STELAE_TOOL_AGGREGATOR_DEBUG_*`) are in-flight to capture exact payloads (files referenced later in findings) so the bridge/Codex mismatch can be isolated.
3. **Positive progress.** The local vs default aggregation split prevents `${STELAE_CONFIG_HOME}` from inheriting repo defaults and keeps tracked manifests clean; docs now emphasize running `process_tool_aggregations.py --scope local` before rendering, and README/ARCHITECTURE explain how optional bundles stay overlay-only.

## Findings

1. **Restart + readiness remain brittle in the harness.** Even after sandbox `.env` fixes, the harness still spends most of its budget inside `run_restart_stelae.sh`, then times out while Codex is mid-stage (`bundle-tools`) (dev/tasks/clone-smoke-harness-stability.md lines 212-219). Without capturing pm2 output and `/mcp` probes to the transcript, contributors cannot tell whether failures stem from pm2, proxy readiness, or Codex CLI stalls.
2. **Catalog publication is still inconsistent for Codex.** HTTP probes and manual tool calls succeed, but Codex agents report invalid JSON coming back from `workspace_fs_read` (`dev/tasks/stelae-mcp-catalog-consistency.md` recent entries). This points to either the FastMCP bridge streaming partial chunks or the aggregator returning richer content than Codex’s schema expects. Until instrumentation proves which component mutates the payload, the harness cannot trust `codex exec --json` as a gating signal.
3. **Task/doc sprawl hides dependencies.** Separate workbook-style task files overlap (clone harness stability vs catalog consistency vs Codex smoke instructions), and README/docs mention the same flows in multiple places. Nothing currently ties “fix catalog publication” to “rerun harness and update progress tracker,” so regressions resurface when the focus shifts.
4. **Docs highlight the local/default separation but lack operational guardrails.** README + ARCHITECTURE describe overlays and aggregation scopes, yet there is no succinct runbook that says “after editing defaults, do X to regenerate local overlays and re-run `pytest tests/test_repo_sanitized.py`.” This gap contributed to the earlier contamination issue and will recur without an explicit checklist.

## Recommended actions (prioritized)

1. **Finish the instrumentation loop.**
   - Enable the new FastMCP/aggregator debug flags in the sandbox (`STELAE_STREAMABLE_DEBUG_TOOLS="*"`, `STELAE_STREAMABLE_DEBUG_LOG`, `STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS="workspace_fs_read,doc_fetch_suite"`) during the next harness run so every request/response pair is persisted alongside `harness.log`.
   - Treat the resulting log as the basis for either fixing JSON framing in the bridge or updating Codex prompts to read from the returned content type.
2. **Restructure the harness tasks/documents.** Replace the three overlapping task files with a single “Stelae smoke readiness” tracker that has clearly staged goals (sandbox bootstrap, restart stability, Codex catalog parity). Keep the detailed run logs as dated appendices instead of mainline checklists.
3. **Document the overlay workflow explicitly.** Add a short “Regenerate overlays safely” section to README/ARCHITECTURE that references `process_tool_aggregations.py --scope default/local`, `make render-proxy`, and `pytest tests/test_repo_sanitized.py`, making it clear when contributors should touch tracked templates vs `${STELAE_CONFIG_HOME}`.
4. **Codex stage focus.** Profile `codex exec --json` outside the harness with the same prompts to prove whether the CLI itself is hanging or if the sandbox env is missing dependencies. Once the root cause is known, bake a regression (e.g., JSONL transcript pattern check) into `scripts/run_e2e_clone_smoke_test.py` so future changes cannot regress silently.
5. **Update `progress.md` + docs together.** Every time catalog/harness fixes land, update `dev/progress.md`, the consolidated task doc, README, and `docs/e2e_clone_smoke_test.md` in the same change so the narrative stays aligned.

## Task/doc consolidation proposal

- **New umbrella doc:** `dev/tasks/stelae-smoke-readiness.md` with sections for (a) sandbox bootstrap, (b) catalog publication, (c) Codex harness automation. Each section links to the relevant scripts/tests and carries the living run log.
- **Archive-or-append approach:** Keep the detailed historical notes from the existing five docs, but move them into dated appendices so the main body stays readable. Reference these appendices from `docs/e2e_clone_smoke_test.md` for anyone who needs the blow-by-blow diagnostics.
- **Progress linkage:** `dev/progress.md` should reference only the umbrella doc so there’s a single checkbox to flip when smoke coverage is healthy.

## Outstanding questions / dependencies

1. Does Codex require a manifest reinitialize between harness stages, or can we reuse a session once the initial `tools/list` succeeds? Understanding this affects how we script `codex exec` prompts.
2. Should we expose codex-wrapper as a first-class MCP server in discovery so testers can validate its install/remove cycle, or keep it out-of-band to reduce noise?
3. When do we expect to rerun the Cloudflare worker/tunnel portion inside the harness (currently skipped with `--no-cloudflared`)? Clarifying this will prevent future regressions when remote manifest publication is required.

## Immediate next steps checklist

1. Add and enable the debug env vars in `scripts/run_e2e_clone_smoke_test.py` (behind a flag so we can turn them off during fast runs).
2. Merge the three task docs into the proposed umbrella; leave short “pointer” stubs behind referencing the new location.
3. Add a README/ARCHITECTURE subsection titled “Overlay workflow & regression guardrails” with the explicit renderer/test steps.
4. Schedule a focused Codex CLI profiling session (outside the harness) to capture the `Expecting value` failure with the new debug logs in place.
