$ bash -lc 'cat <<'"'"'EOF'"'"' > HUB.md

# DEPRECATED — historical Stelae hub design

> This document outlines the initial Go-based hub proposal and is kept for reference only. The current bridge implementation lives in `scripts/stelae_streamable_mcp.py`.

# Stelae Hub Design

## Context

Stelae today runs the [TBXark/mcp-proxy](https://github.com/TBXark/mcp-proxy) service inside WSL. Each upstream MCP server (filesystem, ripgrep, shell, docs, memory, search, fetch, strata, …) is spawned as a stdio client and exposed to remote callers through its own SSE endpoint (for example `/fs/sse`, `/rg/sse`).  The proxy also publishes a manifest that flattens every tool/resource so external consumers such as ChatGPT can discover the full tool surface via one public URL.

Codex CLI, however, only speaks the stdio transport.  It cannot consume the SSE manifest directly and therefore requires a single stdio endpoint that already aggregates every tool.  Today the only way to connect Codex is to list each upstream server separately in `~/.codex/config.toml`, launching one stdio↔SSE bridge per server.  That approach diverges from the ChatGPT setup, prevents automatic promotion of new MCPs, and is tedious to maintain.

## Problem

Provide Codex (and any other stdio‑only client) with **one** MCP entry that mirrors the entire Stelae tool surface while keeping the existing SSE proxy untouched for remote clients.

## Decision (ADR)

Create a dedicated **Stelae Hub** component that runs alongside the SSE proxy.  The hub will:

- read the Stelae MCP manifest (local `http://localhost:9090/.well-known/mcp/manifest.json`),
- connect to each advertised SSE server using the existing MCP client protocol,
- merge their tools/prompts/resources into a single in-process `mcp-go` stdio server, and
- expose that server to Codex (or any stdio client) via one executable (`stelae-hub`).

The original proxy remains responsible for starting upstream MCPs and serving SSE to ChatGPT.  The hub focuses on stdio aggregation.

## Benefits

- **Single configuration entry** for Codex: `[mcp_servers.stelae]` that always reflects the latest tool set.
- **No duplication of manifests**: hub consumes the authoritative SSE manifest produced by the proxy.
- **Transport isolation**: SSE clients (ChatGPT) continue using the existing proxy endpoints; stdio clients get a companion endpoint without changing upstream services.
- **Auto-discovery compatible**: Strata and 1mcpserver can promote new MCPs by editing the proxy config only; Codex picks them up after a hub refresh.
- **Explicit layering**: transport conversion (proxy) and aggregation (hub) evolve independently.

## Limitations

- The hub introduces another long-lived process; it must be supervised (PM2/systemd) just like the proxy.
- Initial implementation forwards requests sequentially; high-volume use may require batching or per-server worker pools.
- Tool name collisions must be resolved (either by prefixing with the server name or enforcing an allow list).
- Hub assumes reachable SSE endpoints published in the manifest; misconfigured servers still require proxy-side fixes.

## Functional Requirements

1. Provide a CLI binary `stelae-hub` executable from WSL.
2. Accept at minimum:
   - `--manifest-url` (defaults to `http://127.0.0.1:9090/.well-known/mcp/manifest.json`),
   - `--refresh-interval` (optional: periodic manifest reload),
   - filtering flags (`--allow`, `--deny`, `--namespace-style`).
3. On startup:
   - Fetch manifest JSON.
   - For each `servers[i]` entry, start an SSE client (reusing the `mcp-go` client stack already vendored).
   - Call `initialize`, `tools/list`, `resources/list`, and register handlers that forward to the correct client.
4. Expose a stdio MCP server using `mcp-go/server.NewMCPServer` + `server.NewStdioServer`.
5. Provide a management tool (`stelae.reload`) that forces a manifest refresh on demand.
6. Log lifecycle events (connected/disconnected, tool registration, errors) to a dedicated log file (`logs/hub.out.log` / `logs/hub.err.log`).

## Non-Functional Requirements

- Built with Go ≥1.22 (same toolchain as `apps/mcp-proxy`), statically linked for easy shipping.
- Unit tests for manifest parsing, namespacing, and forwarding logic; integration tests for a small set of mock SSE servers.
- Structured logging compatible with existing log rotation.
- Graceful shutdown: close all SSE clients and drain active tool calls.

## File & Module Layout

```filesystem
stelae/
├── cmd/
│   ├── proxy/              # existing TBXark/mcp-proxy source (vendored)
│   └── hub/                # NEW: main package for stelae-hub
│       └── main.go
├── internal/
│   ├── manifest/           # manifest fetching & parsing helpers
│   ├── sseclient/          # thin wrapper around mcp-go SSE client
│   ├── aggregator/         # tool/resource registration and forwarding
│   └── logging/
├── HUB.md                  # this document
└── ...
```

## Implementation Notes

1. **Manifest fetcher**
   - Reuse existing types from proxy (`Config`, `ServerEntry`) where practical.
   - Support ETag/If-Modified-Since to avoid unnecessary reloads.
2. **SSE client pool**
   - For each server entry create a `client.Client` (mcp-go) pointing at its `url`.
   - Expose metrics: connected/failed/retry counts.
3. **Forwarding**
   - For each tool: register a closure that calls `client.CallTool` and streams the response back through the hub’s stdio session.
   - Use server name + tool name for internal routing; optionally expose plain names if no collision.
4. **Reload path**
   - On trigger: fetch manifest, diff against current state, add/remove clients and tool registrations without restarting the hub.
   - Reject reload while a previous reload is in progress to avoid race conditions.
5. **Deployment**
   - Add a `make hub` target that builds `cmd/hub` into `~/.local/bin/stelae-hub`.
   - PM2 entry (optional) similar to other services:

     ```json
     {
       "name": "stelae-hub",
       "script": "stelae-hub",
       "args": "--manifest-url http://127.0.0.1:9090/.well-known/mcp/manifest.json",
       "env": { "PATH": "${PATH}" }
     }
     ```

   - Codex config:

     ```toml
     [mcp_servers.stelae]
     command = "wsl"
     args = ["stelae-hub"]
     startup_timeout_sec = 30
     tool_timeout_sec = 180
     ```

6. **Monitoring**
   - Add a health-check CLI flag (`--healthcheck`) that prints current connections and exits (for pm2 `--watch` or cron).

## Open Questions

- Do we add optional HTTP diagnostics (pprof/metrics) for the hub?
- Should the hub expose a WebSocket/SSE endpoint mirroring stdio traffic for debugging?
- How do we authenticate when the manifest includes non-local URLs? (Future work: allow per-server auth headers via config overrides.)
- Long-term: should the hub and proxy merge back into one binary once the design stabilizes?

## Next Steps

1. Prototype the manifest → hub pipeline using a subset of servers (fs + rg) to validate forwarding.
2. Finalize CLI surface and namespacing policy.
3. Build full hub, add tests, wire into PM2, update documentation (README, HUB.md).
4. Update discovery scripts (Strata/1mcpserver) to restart or reload the hub whenever proxy config changes.

Once implemented, Codex and other stdio-only clients will consume Stelae through a single, auto-updating MCP interface while the existing SSE proxy continues serving remote agents.
