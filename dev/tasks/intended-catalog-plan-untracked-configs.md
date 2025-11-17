# Catalog Simplification & Bundle Portability (Tracked Config Retirement)

This note refines the enhanced intended-catalog plan with the constraint that **tracked config files must disappear entirely** once a repo is cloned. All mutable data lives in `${STELAE_CONFIG_HOME}` (user-owned) or `${STELAE_STATE_HOME}` (runtime artifacts). The repo ships only code + documentation; no JSON template needs to be touched at runtime.

## 1. Scope & Goals

1. Remove the need for tracked `tool_overrides*.json`, `tool_aggregations*.json`, `tool_schema_status.json`, and `custom_tools.json` by relocating all writable copies to the config home and treating tracked defaults as code. This requires a dedicated migration: move today’s default entries into the Python services (integrator, aggregator, restart helpers), update their tests, and only delete the tracked files once the code path no longer reads them.
2. Keep the intended catalog pipeline (intended → live) by generating `intended_catalog.json` inside `${STELAE_STATE_HOME}` every render, while users only edit their config-home copies or bundle folders.
3. Ensure Stelae’s built-in servers remain available without needing tracked JSON records.
4. Make bundles portable folders that drop into the config home, independent of installation paths for their binaries.
5. Ship bootstrap code that seeds `${STELAE_CONFIG_HOME}/catalog/*.json` (and related bundle folders) with empty JSON so renders succeed immediately even when the user has not authored any catalog data.

## 2. Built-in Servers & Why Tracked JSON Is Unnecessary

Stelae ships five core servers/tools today:

| Component | Reason tracked configs are unnecessary |
| --- | --- |
| `stelae_integrator_server.py` | Not exposed via aggregations; overrides are applied directly in the Python server. |
| `tool_aggregator_server.py` | Same story—internal defaults live in code. User-defined aggregates reside only in config-home files/bundles. |
| `public_mcp_catalog` helper | Configured in code/pm2 definition; no JSON overrides needed. |
| `stelae_one_mcp` (1mcp stdio agent) | Only existed in `tool_aggregations.json` so it could be disabled. We can read a `STELAE_ONE_MCP_ENABLED` env var or config-home flag instead, eliminating the tracked entry. |
| `stelae_facade` (FastMCP bridge) | Same as above; make enablement flag-driven instead of tracked override entries. |

Net effect: `config/tool_aggregations.json` and `config/tool_overrides.json` become empty and can be deleted. All runtime merging happens between `${STELAE_CONFIG_HOME}/catalog/*.json` (user entries, including bundles) and `${STELAE_CONFIG_HOME}/bundles/*/catalog.json`.

## 3. File Location Changes & Minimal Templates

We still ship the templates/schemas required for bootstrap—most importantly `config/proxy.template.json`, which remains tracked so the Go proxy wiring stays reproducible. Setup scripts seed `${STELAE_CONFIG_HOME}` from these read-only templates on first run, but day-to-day operation touches only the user-owned copies.

All mutable files move out of the tracked tree:

| File | Old location | New location | Notes |
| --- | --- | --- | --- |
| `tool_schema_status.json` | Previously tracked + mirrored | `${STELAE_STATE_HOME}/tool_schema_status.json` | Runtime artifact owned by renderers/proxy. Clearing it wipes telemetry without touching git. |
| `custom_tools.json` | `config/custom_tools.json` | `${STELAE_CONFIG_HOME}/custom_tools.json` | Users add/remove custom scripts here; tracked repo stays clean. |
| `discovered_servers.json` | `config/discovered_servers.json` | `${STELAE_STATE_HOME}/discovered_servers.json` | Fresh clones start empty; operators populate it via discovery runs instead of inheriting dev-curated entries. |
| Bundle payloads | `config/bundles/*.json` | `${STELAE_DIR}/bundles/<name>/bundle.json` (tracked definition) + runtime drop-in under `${STELAE_CONFIG_HOME}/bundles/<name>/` | Repo still ships canonical bundle folders for sharing. Applying a bundle = copying its folder into the config home. |

`intended_catalog.json` continues to be emitted into `${STELAE_STATE_HOME}` alongside `.prev` and optional timestamped copies so the proxy + diagnostics retain a single materialized view, but it is no longer tracked. During bootstrap, `process_tool_aggregations.py` (or `scripts/setup_env.py`) ensures `${STELAE_CONFIG_HOME}/catalog/core.json` and any other required files exist as empty `{}` blobs so an initial render never fails due to missing inputs. Bundles follow the same rule: the first time a bundle name appears, the helper creates the folder with a stub `catalog.json` until the installer runs.

## 4. Bundle Packaging & Installation

- **Format:** A bundle is a folder containing a combined `catalog.json` (servers + aggregates + hide rules) plus optional helper scripts/configs. Dropping the folder into `${STELAE_CONFIG_HOME}/bundles/<name>/` activates it; removing the folder uninstalls it. No tracked overlay files are touched.
- **Install command + launch checks:** `stelae bundle install path/to/bundle-folder` copies the folder into `config_home/bundles/` and registers each server’s `installRef` (GitHub repo, package name, etc.) in a per-user install state file. On every launch/render we read those refs; if a bundle entry lacks a matching install marker we run its `install.json` (or equivalent) check, install if missing, then persist the marker. Future bundles referencing the same `installRef` reuse the existing install and only hydrate their catalog entries. This keeps bundle installs idempotent without mutating tracked files and limits each server to one user-wide installation.
- **Runtime merge:** Renderers load every `catalog.json` inside `${STELAE_CONFIG_HOME}/bundles/*/` plus any user-authored `config_home/catalog/*.json`, merge them via the existing overlay machinery, and emit the intended catalog. Bundles do not pollute user overlay files because each bundle maintains its own folder and can be deleted wholesale, and proxy wiring merges stay in-memory—`proxy.template.json` never changes at runtime.
- **Auto-install hooks:** Bundles may include an `install.json` (or extend `proxy.json` schema) specifying commands to run if prerequisites are missing. Those commands run relative to the bundle folder; they are not tied to `${STELAE_CONFIG_HOME}` paths, so binaries can reside anywhere.

## 5. Disabling Built-in Tools Without Tracked Aggregations

For `one_mcp` and `facade`, expose enable/disable toggles in `${STELAE_CONFIG_HOME}/stelae.defaults.json` (or environment variables). Renderers read those flags and skip adding the servers to the intended catalog when disabled. The Go proxy will hide all `one_mcp` tools by default (no tracked hidden-tools list required), and targeted overrides live in code, so the aggregator helper never needs a tracked entry just to flip `enabled: false`.

## 6. Runtime Workflow After Cleanup

1. **Render:** `make render-proxy` invokes `process_tool_aggregations.py`, which now only reads user/bundle `catalog.json` files. It writes `intended_catalog.json` + `.prev` into `${STELAE_STATE_HOME}` and updates `tool_schema_status.json` in `${STELAE_STATE_HOME}` (clearing the file simply resets telemetry).
2. **Proxy:** Reads intended catalog from `${STELAE_STATE_HOME}` and writes `live_catalog.json` back into the same directory. No tracked files change.
3. **Bundles:** Users add/remove bundle folders whenever they want. Renderers pick them up automatically on the next run; uninstalling is equivalent to deleting the folder.
4. **Schemas:** `tool_schema_status.json` stays in `${STELAE_STATE_HOME}`; removing it resets schema adoption attempts without touching git, and bootstrap helpers recreate an empty file automatically.
5. **Discovery:** `discovered_servers.json` moves to `${STELAE_STATE_HOME}` and behaves like `live_catalog.json`—purely runtime, never tracked.

## 7. Follow-up Work

1. Migrate tracked defaults (`tool_overrides*.json`, `tool_aggregations*.json`, `custom_tools.json`) into server code/tests, then delete the files once the integrator/renderer no longer reference them.
2. Update render scripts + documentation to point all mutable files to the config home / state home per the table above.
3. Implement bundle folder loading + runtime merge logic (and matching uninstall docs).
4. Add enable/disable flags for `one_mcp` and `facade` in a config-home file so tracked aggregations are unnecessary.
5. Move discovery outputs into `${STELAE_STATE_HOME}` and adjust tests/CLI helpers accordingly.
6. Keep intended/live catalog instrumentation as described in the enhanced plan, but decouple it from tracked templates entirely.
7. Split bundle validation/UX improvements into a follow-up task so catalog/state cleanup can land independently.

This design leaves the repo pristine during operation, gives users and bundle authors a clear "drop-in/out" workflow, and retains the benefits of the intended/live catalog pipeline without requiring any tracked JSON overlays.

## Status – 2025-11-17

### What’s implemented so far

- Embedded defaults: tool overrides/aggregations, custom tools, discovered servers now live in code (no reliance on tracked JSON to bootstrap) and seed `${STELAE_CONFIG_HOME}`/`${STELAE_STATE_HOME}` when missing.
- Config-home scaffolding: `ensure_config_home_scaffold` creates catalog/bundle placeholders only; no defaults file is written.
- Intended/live catalogs: `scripts/process_tool_aggregations.py` emits `${STELAE_STATE_HOME}/intended_catalog.json`; `scripts/capture_live_catalog.py` + restart hook capture `${STELAE_STATE_HOME}/live_catalog.json`.
- Bundle folders: loaders/tests support folder-based bundles with install refs and catalog fragments.
- Visibility toggles: `STELAE_ONE_MCP_VISIBLE` / `STELAE_FACADE_VISIBLE` mark those servers disabled in the intended catalog (hidden from tools/list) while keeping them running for internal consumers.
- Safety tests: coverage added around catalog store, defaults seeding, custom tools seeding, live catalog capture, bundle install, and proxy render visibility handling.

### What remains / follow-up guidance

1) Remove tracked JSON templates once callers stop reading them:
   - `config/tool_overrides.json`, `config/tool_aggregations.json`: adjust `scripts/process_tool_aggregations.py --scope default` and related tests (`tests/test_repo_sanitized.py`, aggregator tests) to use embedded defaults or config-home seeds instead of tracked files.
   - `config/custom_tools.json`, `config/discovered_servers.json`: ensure no bootstrap path copies these tracked files; switch any remaining code to embedded defaults/config-home and update docs/tests accordingly.
   - `config/tool_schema_status.json`: point defaults/env to the state path only and update docs/tests so the tracked placeholder can be deleted.
2) Renderer/restart alignment:
   - Confirm restart/proxy wiring uses intended/live catalogs exclusively and no longer references tracked overrides/aggregations paths.
   - Update README/ARCHITECTURE to reflect “no tracked JSON needed” once the above deletions land.
3) Tests/docs cleanup:
   - Revise `tests/test_repo_sanitized.py` expectations once tracked JSONs are removed.
   - Add a short note in README on the visibility env vars (done) and ensure any CLI guidance reflects config-home/state-only sources.
4) Verify-clean path:
   - After deleting tracked JSONs, rerun `python scripts/process_tool_aggregations.py --scope default/local`, `make render-proxy`, `pytest`, and `make verify-clean` to ensure the render/restart loop stays idempotent with the new sources.

Open questions for follow-up

- Do we want a small compatibility shim so `--scope default` reads embedded defaults when the tracked files no longer exist, or retire that scope entirely? Answer: We want as few moving parts as possible and don't need extra flags if they are not supposed to be changed at all once deployed.
- Should we preserve minimal stub JSONs for docs/examples, or remove them outright once tests are updated? Answer: Remove them outright once that is possible.

### Phased execution plan (entry/exit criteria and concrete steps)

Phase 1 – Config path refactor (env-first, no fallbacks)

- Entry: agreement to make `${STELAE_CONFIG_HOME}` / `${STELAE_STATE_HOME}` the only mutable roots; goal to stop reading tracked JSONs entirely.
- Steps:
  1. Add/confirm env variables for every mutable path (e.g., `CATALOG_STORE`, `TOOL_OVERRIDES_PATH`, `TOOL_SCHEMA_STATUS_PATH`, `STELAE_CUSTOM_TOOLS_CONFIG`, `STELAE_DISCOVERY_PATH`) in `.env.example`, pointing at `${STELAE_CONFIG_HOME}`/`${STELAE_STATE_HOME}`. Avoid `.local` naming for paths without tracked counterparts.
  2. Update loaders to consume those env vars first and drop silent fallback to repo paths; fail fast if unset/missing.
  3. Teach renderers/restart scripts to surface the required envs (messages or validation) so users know which vars must exist.
- Exit: All mutable reads/writes flow through env-configured paths under config/state homes; no code path reads repo JSON for runtime data.

Phase 2 – .local naming removal and template deletion

- Entry: Phase 1 envs wired; code can operate without tracked JSON presence.
- Steps:
  1. Delete tracked mutable JSONs (`config/tool_overrides.json`, `config/tool_aggregations.json`, `config/custom_tools.json`, `config/discovered_servers.json`, `config/tool_schema_status.json`).
  2. Rename any remaining `.local`-only filenames to plain names in `${STELAE_CONFIG_HOME}` (e.g., `tool_overrides.json` instead of `tool_overrides.local.json`) and adjust readers/writers/tests accordingly.
  3. Update proxy template/env defaults to point at the new names and ensure renderers don’t recreate `.local` files.
- Exit: Repo contains only schemas/templates that are truly read-only (e.g., `proxy.template.json`, schemas); config-home/state files use non-`.local` names and are the sole writable copies.

Phase 3 – Loading and seeding alignment

- Entry: File layout finalized (Phase 2).
- Steps:
  1. Update bootstrap/seeding helpers (`setup_env.py`, integrator, catalog store, aggregator server, discovery seeding, custom tools server) to create empty JSON stubs in config/state homes when missing, using env vars for paths.
  2. Ensure catalog store merges embedded defaults with config-home fragments/bundles only; no repo reads.
  3. Adjust bundle installer to write catalog fragments directly under `${STELAE_CONFIG_HOME}/bundles/<name>/catalog.json` without touching overlays.
- Exit: Fresh clone + `python scripts/setup_env.py --materialize-defaults` (or restart flow) succeeds with no tracked JSON present; intended catalog emits from config/state content only.

Phase 4 – Test and doc adaptation

- Entry: Runtime behavior stable under new paths/names.
- Steps:
  1. Update pytest fixtures/expectations (`tests/test_repo_sanitized.py`, aggregation/overrides/custom-tools tests, bundle tests) to stop referencing deleted tracked files and to assert env-driven locations.
  2. Refresh README/ARCHITECTURE/AGENTS to document the env-first paths, new filenames (no `.local`), and the deletion of tracked mutable JSONs.
  3. Run `python scripts/process_tool_aggregations.py --scope default/local`, `make render-proxy`, `pytest`, `make verify-clean`; document any required new checks (e.g., env validation) in the release checklist.
- Exit: Test suite and docs pass/read clean without tracked mutable JSONs; verify-clean stays empty after render/restart.

Feasibility note

- If all phases can be applied in one session (small code surface, limited test fallout), proceed end-to-end. If scope grows (e.g., pervasive path changes or test churn), split the work and delegate via codex-wrapper per docs/codex-wrapper-instructions.md, one phase at a time, keeping this task doc as the orchestrator plan.

Progress log
- Completed Phase 1: env-driven paths under config/state homes with fail-fast validation; loaders/renderers/integrator/aggregator/custom-tools/populate scripts updated; `.env.example` lists required paths.
- Completed Phase 2: removed tracked mutable JSONs; config-home files use plain names (no `.local`); tests/docs/code updated to stop referencing tracked templates or `.local` names.
- Remaining Phase 3: confirm bootstrap/bundle flows only create/read config-home/state files (no `.local` recreation) and that bundle installer writes catalog fragments directly under `${STELAE_CONFIG_HOME}/bundles/<name>/catalog.json`.
- Remaining Phase 4: full doc sweep for any lingering `.local`/tracked-config mentions and optional restart/bundle smoke under the new layout; run `make render-proxy`/`make verify-clean` once ready.
