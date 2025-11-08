# Task: Automate 1mcp Discovery → Stelae Stack Integration

Related requirement: `dev/progress.md` → Requirement Group A → “Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides”.

Tags: `#automation`, `#infra`, `#mcp`

## Goal

Ship a single MCP server (`stelae-integrator`, exposing one `manage_stelae` tool) that can turn 1mcp discovery output into a fully wired Stelae configuration. Instead of registering many tiny tools, this server accepts an `operation` enum and delegates internally, keeping the manifest lean while still enabling rich automation. After discover→install, the new downstream server should:

- be present in `config/proxy.template.json` with the right transport/args/env;
- have `config/tool_overrides.json` seeded with default tool names/descriptions (leveraging the override pre-population task);
- trigger render + restart (`make render-proxy`, `scripts/restart_stelae.sh --full`), republishing the manifest;
- return a report so operators know what changed.

The workflow should also cover manual JSON blobs and provide guardrails (dry-run, validation, failure recovery). This supersedes the earlier “override automation” task; that functionality becomes a sub-step here (with a fallback CLI in case someone adds servers manually).

## Checklist

- [ ] Define the interface for discovery ingestion (JSON schema sourced from 1mcp, stored under `config/discovered_servers.json`).
- [ ] Implement the MCP server:
  - Expose a single tool, `manage_stelae`, with an `operation` enum (`list_discovered_servers`, `install_server`, `refresh_discovery`, `run_reconciler`, etc.) and operation-specific `params` validated via a discriminated union schema.
  - Optional operations cover `remove_server`, `dry_run_install`, or future reconciler automation.
- [ ] Normalise discovery descriptors:
  - Map transports (`stdio`, `http`, `streamable-http`).
  - Capture command/args/env or URL headers.
  - Persist display metadata for overrides (`description`, upstream repo).
- [ ] Update `config/proxy.template.json` programmatically:
  - Merge entries alphabetically to keep diffs neat.
  - Ensure `.env` keys exist and binaries are resolvable; surface actionable errors.
- [ ] Seed `config/tool_overrides.json` for new tools:
  - Reuse the “prepopulate defaults” logic now implemented by `scripts/populate_tool_overrides.py`.
  - Provide a command-line fallback (e.g., `scripts/populate_tool_overrides.py --servers <name> --dry-run`) in case servers are added manually or discovery is disabled.
- [ ] Execute `make render-proxy` and `scripts/restart_stelae.sh --full` inside the tool, streaming logs and catching failures (fail fast with clear messaging).
- [ ] Add regression tests:
  - Unit tests for config merge/sanitisation.
  - Integration test spinning the MCP server in-process (simulate discovery JSON → verify config edits + restart command invocation via mock).
- [ ] Document the workflow:
  - README section (“Installing servers discovered by 1mcp”).
  - Task instructions referencing how this replaces `override-automation`.
  - Notes on dry-run, auth handling, and failure fallbacks.
- [ ] Update progress tracker/task log once the automation lands.

## Implementation Notes

### Discovery Cache

- Expect 1mcp to write `config/discovered_servers.json` (one array of entries).
- Each entry should include: `name`, `transport`, `command` or `url`, optional `args`, `env`, `description`, `source` (Git repo / manifest URL), `tools` (names/descriptions if known), `requiresAuth` flag.
- The integrator should gracefully handle missing fields and mark entries as “incomplete”.

### Config Update Workflow

1. Load discovery cache → validate selected entry.
2. Update template:
   - For stdio, set `type: "stdio"` and fill `command` & `args`.
   - For HTTP/streamable servers, set `type: "http"` or `"streamable-http"` and the endpoint URL/headers.
   - Allow optional `options` block (panicIfInvalid/logEnabled/toolFilter/authTokens).
3. Update overrides:
   - Insert master-level entries for each exposed tool if not present, using discovered descriptions.
   - Preserve `servers.*` blocks for per-server hints.
4. Persist files (ensure trailing newline, sorted keys to minimise churn).
5. Run render + restart; capture output for the user.
6. Return a JSON response with `status`, `files_updated`, `commands_run`, and any warnings.

### Guardrails & Recovery

- Support `dryRun` → emit proposed diffs (maybe via unified diff) without applying.
- Detect existing entries: if a server already exists, either skip, update, or prompt the caller (configurable) and report that state in the JSON response.
- Validate binaries via `shutil.which` (Python) or `os.stat`; if missing, abort with instructions.
- If restart fails, surface the error, include captured stdout/stderr, and return the commands the user can run manually.
- Provide a CLI alias (e.g., `python -m stelae_integrator --operation install_server --dry-run`) that reuses the same dispatcher for non-MCP flows (CI, manual maintenance).

### Admin Tool Schema & Dispatch

- **Input schema:** top-level object with `operation` (enum) and optional `params`. Use `oneOf` on `params`, keyed by `operation`, so `list_discovered_servers` needs no extra fields, `install_server` requires `slug` or full descriptor, `run_reconciler` requires `capability` + `target`, etc.
- **Output schema:** consistent envelope containing `status`, `details`, `files_updated`, `commands_run`, `warnings`, and `errors`. Every operation returns the same envelope so clients can parse results uniformly.
- **Dispatch:** map each `operation` to a helper inside the server. Helpers call the shared libraries this task introduces (config merge, overrides seeding, restart orchestration, reconciler integration, 1mcp discovery) rather than shelling out unless necessary. Centralise locking, dry-run diffing, and logging in the dispatcher to keep behavior identical whether invoked via MCP or CLI.

### Reference: Docy Manager Pattern

- The Docy source manager (see `dev/tasks/docy-source-manager.md`) demonstrates the per-server approach: keep a declarative JSON catalog under `config/`, render any generated artifacts via a Python renderer, and expose a single MCP/CLI tool with an `operation` enum for list/add/remove/sync tasks.
- Reuse that pattern for the integrator: treat each managed surface (Docy, custom tools, discovered servers) as data + renderer combos, and have the MCP tool orchestrate updates plus any follow-up commands (renderers, restarts) while keeping manifests free of extra tool entries.

### Testing Strategy

- Unit tests for JSON merge functions (no file I/O, pure data transforms).
- Mock-based tests for subprocess invocation (ensure correct command order & args).
- End-to-end test using a temp workspace: write a discovery stub, run `install_server`, assert config + overrides + manifest outputs updated.
- Harness should avoid hitting real binaries; use environment variables to point to fixture scripts.

### Rollout Steps

1. Implement and test the MCP server + CLI helpers.
2. Document usage and add task log entry.
3. Update `make render-proxy` / `restart_stelae.sh` docs to mention the new automation.
4. Consider adding a `make install-server NAME=...` wrapper that calls the MCP tool for non-agent workflows.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] Progress tracker updated
- [ ] Task log updated
- [ ] Checklist completed
