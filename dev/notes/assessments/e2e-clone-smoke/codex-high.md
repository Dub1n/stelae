# Stelae MCP: Clone Smoke Test Recovery, Catalog Hygiene, and Doc Consolidation — codex-high Assessment (2025-11-13)

## Context

- README.md:31-35 and docs/ARCHITECTURE.md:15-19 now spell out the split between the tracked core template (integrator, aggregator helper, proxy) and the optional starter bundle (filesystem/ripgrep/documentation catalog/etc.) so overlays in `${STELAE_CONFIG_HOME}` stay machine-local.
- Recent work (fd0aa59..4b01248) centered on the Codex-driven clone smoke harness plus catalog hygiene. The harness provisions a disposable workspace, installs the starter bundle without touching the host, mirrors Codex config, runs pytest/`make verify-clean`, and drives scripted Codex missions (docs/e2e_clone_smoke_test.md:1-150).
- While iterating on the harness we tightened the tool aggregation story so only curated composites (e.g., `workspace_fs_read`, `doc_fetch_suite`) appear in manifests; templates now track only the documentation catalog aggregate, and `scripts/process_tool_aggregations.py --scope local` writes the optional suites into `${STELAE_CONFIG_HOME}` (dev/tasks/stelae-tool-aggregation-visibility.md:23-34).

## Timeline & Changes (Nov 10–12)

1. **fd0aa59 infra: add e2e clone smoke test harness** introduced `scripts/run_e2e_clone_smoke_test.py` and associated docs/tests.
2. **15683c3 / 6c5629a** layered automation hardening: structured transcripts, pytest + `make verify-clean`, and Codex prompt scaffolding.
3. **9d2d888 / 64bfb0f / 4066ccc / 9f97ea1** documented repeated harness stalls—timeouts at 120 s/300 s/1200 s when pm2 restarts collided with the always-on dev proxy bound to `:9090` (dev/tasks/clone-smoke-harness-stability.md:24-55).
4. **4d427b8 / a3ad43d / a073704** added pytest bootstrapping inside the sandbox, manual-stage prompts, and stronger Codex expectations (workspace_fs_read, doc_fetch_suite, manage_stelae). These runs surfaced schema regressions in the aggregated tools, blocking Codex catalog trials (dev/tasks/stelae-mcp-catalog-consistency.md:21-37).
5. **a46a1ed project: enforce core tool aggregation defaults** refactored aggregation JSON/templates, deduped `enum`/`required` entries, locked defaults vs overlays, and added targeted tests (tests/test_tool_aggregations.py, tests/test_streamable_mcp.py) to prevent duplicate schemas.
6. **182a2ba / fe5ff16** updated README + ARCHITECTURE to highlight that aggregates now live only in local overlays and must be rendered via the installer.
7. **4b01248 project: stelae mcp catalog fix** changed `scripts/tool_aggregator_server.py` so FastMCP skips argument validation (new `PassthroughFuncMetadata`) and forwards JSON payloads exactly as Codex supplies them, addressing the immediate schema mismatch.
8. **Uncommitted (scripts/stelae_streamable_mcp.py, stelae_lib/integrator/tool_aggregations.py)** add opt-in debug logging (`STELAE_STREAMABLE_DEBUG_TOOLS`, `STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS`) that snapshots tool args/results to `logs/streamable_tool_debug.log` or a caller-provided path to chase the remaining `Expecting value: line 1 column 1` errors reported by Codex.

## Regression Summary

- **Harness restarts clashing with dev stack:** Despite randomizing `PROXY_PORT`, the rendered proxy template and pm2 ecosystem still defaulted to `:9090`, so smoke runs tried to start a second proxy on the developer’s port and stalled until the outer timeout (dev/tasks/clone-smoke-harness-stability.md:46-55). Fixes landed to propagate the random port through `.env`, renderer, and pm2, but the doc still labels this as a watch item.
- **Catalog drift after aggregation overhaul:** Aggregated schemas leaked duplicate `required` values, so Codex rejected `doc_fetch_suite`/`workspace_fs_read` outright (`Invalid schema… has non-unique elements`, dev/tasks/stelae-tool-aggregation-visibility.md:23-33). The dedupe pass plus new tests address this, and README/ARCHITECTURE now explain why only local overlays should define non-core aggregates (README.md:33-35).
- **Bridge/tool call parsing failures:** Even after dedupe, Codex’s `workspace_fs_read` invocation fails with `Expecting value…` despite HTTP calls succeeding; latest runs show the proxy returning 200 but Codex crashing while parsing the FastMCP response (dev/tasks/stelae-mcp-catalog-consistency.md:48-56). The in-flight debug hooks aim to capture the JSON emitted by the bridge and aggregator to pinpoint whether we are sending plain text, double-encoded strings, or non-UTF8 bytes.

## Positive Outcomes

- Starter bundle vs core template split is now explicit, preventing tracked configs from being polluted by optional stacks (README.md:31-35, docs/ARCHITECTURE.md:15-19).
- Aggregation pipeline enforces dedupe + hide semantics and ships regression tests so catalogs stay trustworthy (`tests/test_tool_aggregations.py::test_aggregation_runtime_dedupes_and_hides`).
- Clone harness bootstraps `pytest` inside each sandbox, mirrors Codex config, records JSONL transcripts per stage, and exposes manual checkpoints so investigations no longer mutate the host dev environment (docs/e2e_clone_smoke_test.md:33-75, 129-139).

## Outstanding Questions

1. **FastMCP payload fidelity:** Is the bridge still wrapping aggregator responses in text blocks that Codex expects to be JSON? Need concrete samples via `STELAE_STREAMABLE_DEBUG_TOOLS=*` and the new aggregator debug envs.
2. **Harness stage boundaries:** Manual-stage `install` still times out during the Codex `bundle-tools` stage even with 300 s timeouts (dev/tasks/clone-smoke-harness-stability.md:130-165). Do we need to pre-open the MCP channel earlier or rework prompts to keep Codex from over-exploring?
3. **Task sprawl:** We currently track overlapping efforts in five task docs (`dev/tasks/e2e-clone-smoke-test.md`, `clone-smoke-harness-stability.md`, `stelae-tool-aggregation-visibility.md`, `stelae-mcp-catalog-consistency.md`, `codex-manage-stelae-smoke.md`). Each partially duplicates context, making it hard to see blockers vs regressions at a glance.

## Recommended Next Steps

1. **Instrument + reproduce the Codex parse failure.**
   - Enable the new debug envs (`STELAE_STREAMABLE_DEBUG_TOOLS=workspace_fs_read,doc_fetch_suite,manage_stelae`, choose a log path under `logs/`), rerun `codex exec --json` bundle stage, and capture both FastMCP and aggregator logs.
   - Add a small pytest (e.g., `tests/test_streamable_mcp.py::test_workspace_fs_read_roundtrip`) that stubs an MCP call through `scripts/stelae_streamable_mcp.py` so we can diff the JSON we expect vs what Codex receives.
2. **Consolidate task tracking.**
   - Fold the five task docs into a single “Clone smoke & catalog reliability” epic with subsections for harness automation, Codex catalog publication, and documentation hygiene. Preserve historical timelines as dated sub-sections so context stays discoverable, but keep the live checklist front-and-center.
   - Move transient run logs (per-date bullet lists) into `dev/notes/run-logs` so the task doc remains a plan/checklist rather than a diary.
3. **Doc restructure.**
   - Dedicate a README section to “Runtime overlays & starter bundle workflows” that links directly to the smoke harness doc; highlight the new debug envs and the rule that aggregates outside the core template must be rendered via the installer.
   - In docs/ARCHITECTURE.md, expand the “Catalog Aggregation & Overrides” section with a short “Debugging” subsection that enumerates the env knobs and expected manifest states before/after running `scripts/process_tool_aggregations.py --scope local`.
4. **Harness UX polish.**
   - Teach `scripts/run_e2e_clone_smoke_test.py` to fail fast if pm2 is already bound to the requested port (surface the reason instead of waiting for the outer timeout) and to stream Codex JSONL output even when the stage aborts, so runs like the current `bundle-tools` stall have actionable artifacts.
   - Once the FastMCP payload issue is resolved, rerun the full bundle/install/remove stages, archive the passing transcripts under `logs/` as the new baseline, and wire the expectation list back into the harness regression suite.
5. **Maintain separation of local vs default overlays.**
   - Keep using `scripts/process_tool_aggregations.py --scope default|local` during releases so tracked configs remain slim. Note this explicitly in the contributor workflow doc to avoid future contamination of `config/tool_overrides.json`.
