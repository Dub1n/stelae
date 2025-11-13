# Task: Stelae smoke readiness (catalog hygiene · harness reliability · Codex orchestration)

Related requirements: consolidated from
`archive/e2e-clone-smoke-test.md`, `archive/clone-smoke-harness-stability.md`,
`archive/stelae-tool-aggregation-visibility.md`, `archive/stelae-mcp-catalog-consistency.md`, and
`archive/codex-manage-stelae-smoke.md`.

Tags: `#infra`, `#tests`, `#docs`

> This workbook now tracks every open item for the clone smoke initiative. The
> legacy task files listed above are archived and point back here so all notes,
> checklists, and run logs live in one place.

## Scope & checkpoints

| Stream | Goal | Status |
| --- | --- | --- |
| Catalog hygiene | Keep the published manifest limited to curated aggregate tools, dedupe schemas, and capture Codex catalog regressions in the harness. | `[~]` (`workspace_fs_read` JSON parsing gap still unresolved) |
| Harness + restart reliability | `scripts/run_e2e_clone_smoke_test.py` finishes clone → bundle → render → restart → Codex stages with bounded retries and diagnostics while keeping git clean. | `[~]` (port preflight + restart probes landed, Codex stage timeouts under investigation) |
| Codex orchestration | Codex CLI + wrapper can run the golden-path `manage_stelae` scenario end-to-end using only MCP calls, with transcripts stored by the harness. | `[~]` (Stage scripts + wrapper integration complete; catalog consistency still blocks “tool missing” flakes.) |

## Workstreams

### Catalog hygiene

- **Goals:** enforce a curated manifest (`manage_docy_sources`, `workspace_fs_*`, `doc_fetch_suite`, `manage_stelae`, etc.), dedupe JSON Schema arrays before they hit Codex, and make the harness fail fast whenever Codex falls back to stale manifests.
- **What’s done:**
  - `scripts/process_tool_aggregations.py --scope local` now renders aggregates into `${STELAE_CONFIG_HOME}` first, guaranteeing tracked templates stay slim and local overrides remain authoritative.
  - `ToolOverridesStore` dedupes `enum`/`required` arrays so rerunning renders can’t corrupt schemas (`tests/test_tool_aggregations.py::test_aggregation_runtime_dedupes_and_hides` + `tests/test_streamable_mcp.py::test_rendered_manifest_contains_only_aggregates` cover this).
  - FastMCP bridge passes downstream payloads verbatim through `PassthroughFuncMetadata`, preventing aggregator schema mismatches and enabling `STELAE_STREAMABLE_DEBUG_*` logging.
- **Still open:**
  - Trials that prove Codex naturally lists `workspace_fs_read`, `doc_fetch_suite`, and `manage_stelae` without hard-coded prompts. Capture successes/failures via `codex-transcripts/*.jsonl` + mirrored tool-debug logs. *(See Appendix B for the current Codex CLI smoke baseline.)*
  - Update docs/README with the precise “overlay workflow & guardrails” so contributors re-run `process_tool_aggregations.py --scope default`, `process_tool_aggregations.py --scope local`, `make render-proxy`, and `pytest tests/test_repo_sanitized.py` after editing tracked templates. *(This change landed as part of Action Plan #3.)*
  - Maintain the `dev/logs/harness/*-streamable-tool-debug.log` snapshots for every harness run until `workspace_fs_read` JSON errors disappear.

### Harness + restart reliability

- **Goals:** bundle install + render + restart finish in <60 s with actionable logs when they do not, randomized ports never collide with a developer’s long-lived proxy, and the harness exits (with diagnostics) whenever pm2 or downstream tools wedge.
- **What’s done:**
  - Restart helper now performs backoff probes against the JSON-RPC `initialize` call, logs the payload that finally passes, and prints the last HTTP status/body on failure.
  - Harness exposes `--restart-timeout`, `--restart-retries`, and `--heartbeat-timeout` so long stalls terminate with pm2 log tails plus `pm2 status` snapshots.
  - Port preflight kills lingering listeners on the chosen `PROXY_PORT` before pm2 starts, then re-validates that the port is clear.
  - Disposable `python-site/` bootstrap ensures `pytest` installs inside the sandbox via `pip --target` even when the host exporter enforces `PIP_REQUIRE_VIRTUALENV`.
  - Debug flags (`--capture-debug-tools`) mirror FastMCP/tool-aggregator logs into both `${WORKSPACE}/logs/` and `dev/logs/harness/` so evidence survives workspace cleanup.
- **Still open:**
  - Diagnose why Codex bundle stages still hit outer timeouts (see Appendix A: 2025‑02‑14 session). Need a reproducible JSONL transcript that demonstrates either `codex exec` stalling or the stack failing to stream responses.
  - Add guardrail tests around `probe_jsonrpc_initialize` and heartbeat timeouts (`tests/test_streamable_mcp.py` follow-up) once the manifest regression is covered.

### Codex orchestration

- **Goals:** Codex CLI + wrapper complete `discover → install (dry-run + real) → reconciler/remove` using only MCP transport while the harness validates catalog state and git cleanliness.
- **What’s done:**
  - `stelae_lib/integrator/catalog_overrides.py` hydrates descriptors (stdio command/env placeholders) during discovery, so installs pass schema validation.
  - FastMCP bridge handles `manage_stelae` locally, so proxy restarts during install/remove no longer sever Codex calls mid-flight.
  - Harness bundle stage script forces Codex to issue `workspace_fs_read`, `grep`, `manage_docy_sources`, and `doc_fetch_suite` even when the catalog omits them, producing actionable failures instead of silent skips.
- **Still open:**
  - Track the golden-path CLI instructions, prerequisites, and verification steps in one place (see Appendix B) and keep that section updated whenever we change orchestrator interactions.
  - Automation must archive `codex-transcripts/<stage>.jsonl` plus the mirrored debug logs for every CI/manual run so catalog regressions are obvious.
  - Once catalog hygiene stickiness is verified, add a nightly (or on-demand) harness run that uploads transcripts + `logs/streamable_tool_debug.log` as artifacts.

### Automation guardrails

- **Goals:** Bake the renderer/harness guardrails directly into automation so clone runs fail fast when manifests drift or restarts regress, and capture routine smoke artifacts without manual babysitting.
- **Recommended order:** (1) land the manifest/backoff/heartbeat tests so failures show up locally, (2) add the recurring harness run + artifact upload to keep telemetry fresh.
- **Planned work:**
  - [ ] **Preread:** `README.md` (Troubleshooting), `docs/ARCHITECTURE.md` (Catalog Aggregation & Overrides), `tests/test_repo_sanitized.py`, and `docs/e2e_clone_smoke_test.md` (Validation + Feedback) to align test design with published expectations.
  - [ ] Extend `tests/test_repo_sanitized.py` (or add a sibling test) to load a rendered manifest snapshot and assert aggregate names + schema dedupe, plus add unit coverage for `probe_jsonrpc_initialize`/heartbeat timeouts so restart regressions surface without running the full harness.
  - [ ] Schedule (or at least document) a nightly/on-demand clone-harness run that archives `codex-transcripts` and `logs/streamable_tool_debug.log` artifacts, using the existing per-stage log mirroring to simplify uploads.

## Active checklist

- [ ] Trials – Codex CLI wrappers + harness prove `workspace_fs_read`, `doc_fetch_suite`, and `manage_stelae` all register and complete without manual prompts. *(Appendix B documents the current blocker: Codex still reports `Expecting value` from `workspace_fs_read` even though HTTP probes pass.)*
- [ ] Harness reliability – capture a “restart succeeds under 120 s” run with `--capture-debug-tools --manual-stage install` plus logs attached to `dev/logs/harness/`.
- [ ] Codex orchestration – rerun the full golden path (discover → dry-run install → real install → remove) after catalog fixes land and archive the transcripts under `dev/logs/harness/`.
- [ ] Docs/tests – README, `docs/ARCHITECTURE.md`, and `docs/e2e_clone_smoke_test.md` now reference this consolidated task and document the overlay + harness expectations (✅ Action Plan #3).

## References

- Harness code: `scripts/run_e2e_clone_smoke_test.py`, `stelae_lib/smoke_harness.py`, `scripts/run_restart_stelae.sh`.
- FastMCP bridge + aggregator: `scripts/stelae_streamable_mcp.py`, `stelae_lib/integrator/tool_aggregations.py`, `scripts/process_tool_aggregations.py`.
- Integrator flow: `scripts/stelae_integrator_server.py`, `stelae_lib/integrator/catalog_overrides.py`.
- Tests: `tests/test_streamable_mcp.py`, `tests/test_tool_aggregations.py`, `tests/test_codex_exec_transcript.py`, `tests/test_e2e_clone_smoke.py`.
- Docs: `docs/e2e_clone_smoke_test.md`, `README.md`, `docs/ARCHITECTURE.md`.

## Appendices (historical logbook)

### Appendix A – Selected harness sessions

#### 2025‑02‑14 · Restart stall deep dive

- `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 --manual-stage install`
  - Hit the outer timeout while `run_restart_stelae.sh` waited for pm2. Workspace `/tmp/stelae-smoke-workspace-ibh51q3l` retained with `harness.log`.
  - pm2 logs: repeated `Error: write EPIPE` followed by `Failed to start server: listen tcp :9090: bind: address already in use`.
  - Harness selected randomized proxy port (`:22831`) but `mcp-proxy` still booted on `:9090`. Root cause: rendered `proxy.json` still hardcoded the default port (tracked template lacked `{{PROXY_PORT}}`), so pm2 ignored the sandbox value.
- Key findings:
  - `CloneSmokeHarness.__init__` correctly exports `PROXY_PORT`; restart script honors it for port-kill and readiness probes.
  - `ecosystem.config.js` + `config/proxy.template.json` must template `PROXY_PORT`; otherwise pm2 keeps binding to `:9090`. Renderer now patches this path, but older workspaces require regeneration.

#### 2025‑11‑12 · Pytest bootstrap + manual install checkpoint

1. `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py … --manual-stage install --bootstrap-only` warmed workspace in ~6 s (starter bundle installed, pm2 home seeded).
2. `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py … --manual-stage install --skip-bootstrap --reuse-workspace`
   - Restart succeeded; `/mcp` probe passed; structural pytest failed because pip refused to install outside a venv. Fix: set `PIP_REQUIRE_VIRTUALENV=0` during sandbox installs and target `python-site/`.
3. Post-fix validation run reused cached install; manual assets regenerated; harness hit outer timeout while `codex exec … bundle-tools` was running—no transcript captured.
4. Extended timeout (300 s) produced identical outcome: Codex stage still running when timeout fired; restart + pytest pieces solid.

Follow-ups: profile `codex exec --json … bundle-tools`, capture raw JSONL output, and determine whether Codex or the proxy stalls. Artifacts live under `/tmp/stelae-smoke-workspace-dev3/`.

### Appendix B – Codex CLI smoke (`manage_stelae`)

Scenario: prove Codex CLI can drive `discover → install → remove` solely via `stelae.manage_stelae`.

- **Prereqs:** source virtualenv + `~/.nvm/nvm.sh`, run `python scripts/bootstrap_one_mcp.py`, ensure stack healthy (`make render-proxy && make restart-proxy` or `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`), launch Codex CLI profile.
- **Golden path:**
  1. `discover_servers` with `dry_run=true` (query “vector search”, tags `["search"]`, limit `5`). Expect descriptors + `files_updated[0].dryRun=true`.
  2. Dry-run `install_server` using one of the returned names; expect diff-only response.
  3. Real `install_server` streams logs while running `make render-proxy` + restart helper, then waits for proxy readiness.
  4. Optional `run_reconciler` or `remove_server` to verify cleanup.
- **Verification:** `make discover-servers` parity, `scripts/stelae_integrator_server.py --cli --operation list_discovered_servers`, curl manifest to ensure `manage_stelae` stays published.
- **Historical notes:**
  - 2025‑11‑08: descriptors lacked launch commands; installs failed validation. Fix: catalog overrides hydrate stdio command/env placeholders.
  - Install/remove originally dropped MCP responses when the proxy restarted; 2025‑11‑10 bridge change keeps calls local so Codex sees completion even while pm2 flips.
  - Current blocker: `codex exec` occasionally stalls during bundle stages and still surfaces `workspace_fs_read` “Expecting value” even though FastMCP debug logs show valid JSON; logs mirrored via `--capture-debug-tools` until resolved.

### Appendix C – Clone smoke harness deliverable snapshot

- Harness clones Stelae + `mcp-proxy`, provisions isolated `.env`, runs starter bundle with `--no-restart`, seeds a “client repo,” mirrors `~/.codex`, and enforces staged pytest (`tests/test_repo_sanitized.py` immediately, full suite + `make verify-clean` after Codex).
- Codex automation covers three stages (`bundle-tools`, `install`, `remove`) and insists on `workspace_fs_read`, `grep`, `manage_docy_sources`, `doc_fetch_suite`, and `manage_stelae` calls even when the catalog omits them. JSONL transcripts are stored under `${WORKSPACE}/codex-transcripts/` and parsed by `stelae_lib.smoke_harness`.
- Manual fallback flags:
  - `--manual` stops after provisioning and writes `manual_playbook.md` / `manual_result.json`.
  - `--manual-stage <stage>` creates resumable checkpoints—rerun with `--workspace <path> --reuse-workspace` to continue.
- Common CLI flags: `--workspace`, `--keep-workspace`, `--force-workspace`, `--reuse-workspace`, `--cleanup-only`, `--proxy-source`, `--wrapper-release`, `--capture-debug-tools`, `--bootstrap-only`, `--skip-bootstrap`.
- Guardrail: The “install” phase (bundle + render + restart) should complete in <60 s. If “Installing starter bundle…” or “Restarting stack…” stalls longer, investigate orchestration failures (pm2 collisions, env drift, Codex CLI hangs) before raising timeouts.

---

For new work, update this file instead of reviving the archived task docs. Keep appendices chronological so future contributors can see exactly what was tried, what failed, and where to resume.
