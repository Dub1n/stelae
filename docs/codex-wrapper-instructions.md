# Codex MCP Wrapper – SSE Command Endpoint Quickstart

Use this file whenever another repo needs to drive Codex missions over HTTP without embedding the wrapper as an MCP client. The SSE endpoint mirrors the existing `mcp__codex-wrapper-dev__batch` tool, so everything here aligns with that contract.

## Prereqs

1. Clone `codex-mcp-wrapper` and set up the virtualenv:

   ```bash
   cd ~/dev/codex-mcp-wrapper
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```

2. Ensure the Codex CLI is authenticated locally (`codex login`). The wrapper copies `auth.json` into each worker’s isolated `state/workers/<label>/codex-home` on startup.
3. Create or edit `wrapper.toml` with at least one worker definition (see `wrapper.example.toml`).
4. Create a new folder under `logs/<session-name>` and have all the agents write their response output to a file in there with filename `<timestamp>-<session-name>.md` so that progress is captured in case of discontinuation.

## Launching the SSE Server

```bash
codex-mcp-wrapper serve \
  --config /path/to/wrapper.toml \
  --transport sse \
  --host 127.0.0.1 \
  --port 4105
```

* `--transport sse` switches FastMCP into HTTP/SSE mode.
* Host/port can be customized per environment; 127.0.0.1:4105 is the dev default.

## Mission Payload

The `/command` endpoint accepts the exact JSON contract used by `mcp__codex-wrapper-dev__batch`. Minimal example:

```json
{
  "mission": {
    "mission_id": "mission-demo",
    "workspace_root": "/repo/path",
    "tasks": [
      {
        "prompt": "List files",
        "cwd": ".",
        "sandbox": "read-only",
        "approval_policy": "never"
      }
    ]
  }
}
```

Mission files bundled in other repos (e.g., `missions/dev-smoke.json`) can be POSTed as-is.

## Invoking via `curl`

```bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  --data @missions/dev-smoke.json \
  http://127.0.0.1:4105/command
```

`-N` tells curl not to buffer output so SSE events flush immediately.

## Event Stream Contract

The wrapper streams newline-delimited SSE frames:

* `event: log` – text heartbeats for user-friendly status, including dispatcher progress notes.
* `event: progress` – structured payload `{ "mission_id", "progress", "total", "message" }` mirroring `_build_progress_callback` updates.
* `event: result` – final mission response (same JSON schema as the MCP tool, including artifacts and per-task results).
* `event: error` – emitted when mission execution fails or the client disconnects mid-run. Payload includes `mission_id` and `message`.
* `event: done` – terminal sentinel with `{ "mission_id", "status" }` where status is `ok`, `error`, or `cancelled`.

Clients should read until the `done` event arrives; the HTTP connection stays open for the entire mission, with no additional timeouts beyond the configured Codex command timeout (default 900s via `~/.codex/config.toml`).

## Notes for Automation

* Artifacts are still written under `state/missions/<mission_id>/` and referenced in the `result` payload—no extra handling needed.
* The SSE endpoint reuses the dispatcher/worker pool, so every mission behaves exactly like the MCP transport. If it works via `mcp__codex-wrapper-dev__batch`, it works here.
* To cancel work, close the HTTP connection; the server will emit an `error` followed by `done` with status `cancelled`.

Distribute this file alongside mission specs in other repos so agents can bootstrap the wrapper without digging into the full README.
