# Task: Ensure Stelae MCP catalog consistency for Codex agents

Related requirement: `dev/tasks/clone-smoke-harness-stability.md` → Clone smoke harness stability & instrumentation → checklist item “Ensure the Stelae MCP catalog consistently publishes those tools for Codex clients…”.

Tags: `#infra`, `#tests`, `#docs`

## Checklist

- [x] Assessment – audit how the proxy advertises the MCP catalog today (renderer outputs, pm2 env, Codex defaults) and record the current orchestrator/tester experience when connecting to the always-on local stack.
- [x] Research – map the catalog publication flow (proxy manifest, bundle install, harness discovery) and review Codex MCP Wrapper + codex exec mechanics to pinpoint where trusted manifests diverge from runtime tool availability.
- [ ] Trials – use the Codex MCP Wrapper tools (`codex-wrapper-dev.batch`) as the orchestrator plus `codex exec`-spawned Codex agents as testers, iterating changes to the Stelae stack until testers naturally list and invoke required tools (e.g., `stelae.manage_stelae`) via MCP without CLI/curl fallbacks; capture each round-trip result.
- [ ] Update docs/progress/task files (`AGENTS.md`, `dev/tasks/clone-smoke-harness-stability.md`, relevant specs) once the catalog fix and regression harness coverage are implemented.
- [ ] Commit with message `project: stelae mcp catalog fix` after tests.

## References

- Code: `scripts/run_e2e_clone_smoke_test.py`, `scripts/install_stelae_bundle.py`, `scripts/render_proxy_config.py`, `stelae_lib/bundles.py`, `stelae_lib/integrator/core.py`.
- Tests: `tests/test_e2e_clone_smoke.py`, `tests/test_codex_exec_transcript.py`, `tests/test_streamable_mcp.py`.
- Docs: `dev/tasks/clone-smoke-harness-stability.md`, `docs/e2e_clone_smoke_test.md`, `AGENTS.md`.

## Notes

- Source requirement excerpt: “Ensure the Stelae MCP catalog consistently publishes those tools for Codex clients; expand this item into its own task file when work begins so the fix can be tracked independently… Even if the harness can manually invoke the tools, we need a real fix plus a harness regression so the full clone smoke test verifies that agents can discover and call the published tools end-to-end.”
- Initial approach: treat the Codex MCP Wrapper (`codex-wrapper-dev.batch`) as the orchestrator that mutates the local Stelae environment (render/restart, bundle tweaks, catalog pushes). After each change, spawn a fresh Codex agent via `codex exec` to act as the tester; the tester must succeed with out-of-the-box MCP manifests (no CLI shortcuts) and invoke `stelae.manage_stelae` or other published tools through their `mcp__…` handles.
- Success criteria: published tools surface automatically in the agent’s trusted catalog at connect time, the harness captures regressions by exercising orchestrator/tester loops, and documentation explains how to reproduce/verifiy without increasing timeouts.
- Follow-ups: once fixes land, ensure the clone smoke harness runs the new regression path and that `progress.md` plus associated task files reflect the change.
- Prompting note: all Codex missions must run `stelae.manage_docy_sources` (to hydrate Docy sources) before attempting any `stelae.doc_fetch_suite` calls, otherwise the fetch suite will correctly return an empty list even though the tooling is available.
- Catalog boundaries: `codex-wrapper` should stay out of the Stelae tool list for this task; if we decide to surface it later, that will be tracked as a separate change so we can validate the core stack independently.

## Assessment (current)

- pm2 currently has no managed processes (`pm2 status` returned an empty table), so the “always-on” assumption does not hold and `curl http://127.0.0.1:9090/.well-known/mcp/manifest.json` fails locally. Any orchestrator/tester workflow must boot the stack (or reuse the harness sandbox) before checking catalog drift.
- `config/proxy.template.json:2-76` + `scripts/render_proxy_config.py:18-78` prove that only the rendered JSON controls what the Go proxy advertises; the harness writes randomized ports into `.env`/`${STELAE_CONFIG_HOME}`, but pm2 (`ecosystem.config.js:24-65`) always loads `${PROXY_CONFIG}` and defaults back to `:9090` unless that env lands in the runtime.
- `scripts/run_restart_stelae.sh:41-139` already polls `/mcp` via `tools/list` and runs `scripts/populate_tool_overrides.py`, so today’s readiness gate is “catalog count ≥ MIN_TOOL_COUNT.” The missing behavior is ensuring Codex sessions connect only after this gate passes so they inherit the updated catalog instead of reusing stale manifests.
- Trials must therefore begin with `make up`/`scripts/run_restart_stelae.sh --keep-pm2 …` so pm2 is supervising `mcp-proxy`, the bridge, and Cloudflared before we spawn any Codex testers; otherwise every run will revalidate the “stack offline” failure instead of the catalog publication path.
- Local overlays can silently block restarts: `/home/gabri/.config/stelae/stelae/config/tool_aggregations.local.json` still contained an `agg` stub (no description/operations), which tripped `scripts/process_tool_aggregations.py` during every render. Removing that stub let the restart script finish without warnings and ensures tool aggregations stay in sync with the tracked schema.
- `mcp-proxy` will crash on launch unless `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/latest` exists. Built the 0.1.0 wrapper release via `~/dev/codex-mcp-wrapper/scripts/build_release.py` and copied it under `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/0.1.0` so `CODEX_WRAPPER_BIN` resolves; pm2 now keeps `mcp-proxy`, `stelae-bridge`, and `watchdog` online.
- `scripts/restart_stelae.sh` now runs `scripts/process_tool_aggregations.py --scope local` so only user-defined aggregates touch `${STELAE_CONFIG_HOME}` before exporting the runtime JSON. The tracked defaults already live in `config/tool_overrides.json`, and the local pass keeps `tool_overrides.local.json` focused solely on custom entries. After rerender/restart, the HTTP catalog only exposes the aggregate entries (e.g., `workspace_fs_read`, `workspace_fs_write`, `workspace_shell_control`, `doc_fetch_suite`, `scrapling_fetch_suite`, `memory_suite`, `manage_docy_sources`, `manage_stelae`, `batch`, etc.), fixing the “full raw tool list” regression.

## Research (doc updates 2025-02-15)

- Added “Catalog publication & Codex trust boundaries” to `docs/ARCHITECTURE.md` to document the renderer → pm2 → proxy handoff, the FastMCP bridge’s fallback behaviour, and why Codex caches `initialize` results per session (bridged via `scripts/stelae_streamable_mcp.py:61-519`).
- Captured the orchestrator/tester strategy in the same section: the Codex MCP Wrapper (`codex-wrapper-dev.batch`) will own environment mutations while `codex exec --json` sessions act as disposable testers. Harness transcripts (`docs/e2e_clone_smoke_test.md:105-124`) already parse the expected tool calls, so extending them to assert catalog parity gives us a regression guard once the fix is built.
- Confirmed `codex mcp list` still registers `stelae`, `codex-wrapper-dev`, and `templum-bridge`; the CLI launches `scripts/stelae_streamable_mcp.py` (pointing at `http://127.0.0.1:9090/mcp`) whenever a session requests `stelae.*` tools, so we can rely on Codex to bring up the bridge as long as the proxy is healthy.

## Trials (2025-11-12)

1. **Orchestrator (codex-wrapper-dev.batch).** Launched mission `catalog-trial-orchestrator-1` via the MCP tool to snapshot `pm2 status`. The wrapper failed with `EPERM`/`EACCES` while touching `/home/gabri/.pm2/{interactor,rpc}.sock`, so the orchestrator cannot currently inspect process state from its sandbox (captured directly in the tool response). Need either read access to `.pm2` or an alternate readiness probe for wrapper-driven missions.
2. **Tester attempt A (codex exec --json --full-auto …tools/list…).** Prompted a Codex agent to “run tools/list” before hitting the other tools. The run (`logs/codex-catalog-trial-bundle-tools.jsonl`) timed out after 10 min because Codex kept searching for a callable `tools/list` action inside the catalog (it tried `discover_server_actions`, `execute_action` proxies, and even `manage_stelae tools_list`, all of which returned “server not connected” or “unsupported operation”). Conclusion: expecting the agent to issue protocol-level `tools/list` isn’t realistic; we should verify availability indirectly via concrete tool calls instead.
3. **Tester attempt B (codex exec --json --full-auto …workspace_fs_read/doc_fetch_suite/manage_stelae…).** Second run (`logs/codex-catalog-trial-tools.jsonl`) succeeded end-to-end:
   - `workspace_fs_read` read `README.md` without issue, proving the aggregate tool surfaced immediately in the Codex catalog.
   - `doc_fetch_suite` executed but returned `Available documentation sources: []`, which means the Docy server is reachable yet no sources are currently synced. That matches today’s local config and should be documented so the harness treats an empty list as “tool available but empty dataset.”
   - `manage_stelae` initially rejected arguments when Codex wrapped them under `arguments=…`; the fourth call passed `{"operation":"list_discovered_servers"}` at the top level and succeeded, listing the discovered servers (no `codex-wrapper` entry yet). This confirms the tool is callable via MCP; we still need to decide whether codex-wrapper should appear in discovery to satisfy the original requirement.
4. **Artifacts.** Stored both transcripts for comparison: `logs/codex-catalog-trial-bundle-tools.jsonl` (failure) and `logs/codex-catalog-trial-tools.jsonl` (success). These align with the harness expectations, so once we codify them into tests we can diff successive runs automatically.
5. **Harness prompt update.** `scripts/run_e2e_clone_smoke_test.py` now requires Codex to call `manage_docy_sources` (`operation=list_sources`) before `doc_fetch_suite`, and the manual mission (`dev/tasks/missions/e2e_clone_smoke.json`) mirrors that ordering so doc fetch never runs before the Docy catalog is hydrated.
6. **codex-wrapper orchestrator mission.** Added `dev/tasks/missions/stelae_catalog_orchestrator.json` and attempted to run it through `codex-wrapper-dev.batch`. After wiring the worker `CODEX_HOME` instances with an HTTP `stelae` MCP server entry, the mission still fails because the downstream Codex MCP worker reports `unknown MCP server 'stelae'` even though the config lists it. Need to debug why the worker refuses to initialize that server (possibly because the HTTP endpoint is trust-scoped or because `codex mcp-server` ignores entries unless the workspace root is trusted inside `config.toml`).
7. **Latest Codex tester run (2025-11-12 13:32Z).** Re-ran `codex exec --json` with the updated prompt (tool list + `workspace_fs_read`, `manage_docy_sources`, `doc_fetch_suite`, `manage_stelae`). The run (`logs/codex-catalog-trial-tools-v2.jsonl`) now fails before making any calls because the proxy returns `Invalid schema for function 'mcp__stelae__doc_fetch_suite': ['operation', 'operation'] has non-unique elements.` The HTTP manifest shows duplicate enum/required entries for several aggregate tools (`tools/list` reveals `doc_fetch_suite.inputSchema.required = ["operation","operation"]`), which stems from the overrides + server descriptor merge strategy. Need a dedupe step (either in the aggregator renderer or when exporting overrides) so `required`/`enum` arrays remain unique and Codex can register the tools again. **Update (2025-11-13):** `project: stelae aggregation visibility fix` addressed this by deduping JSON Schema arrays and splitting the renderer into `--scope default` / `--scope local`, so the next catalog trials should proceed past initialization.

## Follow-up tasks

1. **codex-wrapper-dev.batch reliability.** Fix the orchestration mission so `pm2 status` (or an equivalent readiness probe) runs without `.pm2` socket errors and verify the wrapper still performs batch missions end-to-end.
2. **Future trial readiness.** Capture any remaining regression hooks that testers will need (log parsing, harness assertions, docy preflight) so subsequent runs can plug into the same workflow with minimal manual tweaks, then re-run Codex through both entry points (`codex exec --json` and `codex-wrapper-dev.batch`) until they can call the target tools without intervention; record transcripts for each.
3. **Schema cleanup follow-up.** ✅ Completed via `project: stelae aggregation visibility fix` (see `dev/tasks/stelae-tool-aggregation-visibility.md` for the implementation notes). Re-run the Codex catalog missions once the orchestrator/tester loops above are stable.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
