---
updated: 2025-09-28-16:20
---

# stelae MCP stack – architecture spec

## 1. High-level flow

The goal is to present a **single MCP endpoint** (`https://mcp.infotopology.xyz/mcp`) that both local tools (Codex CLI/VS Code) and remote ChatGPT Connectors can rely on. Internally we compose many MCP-capable services, but externally we expose only the minimal tool pair ChatGPT expects: `search` and `fetch`.

```diagram
ChatGPT / Codex ---> Cloudflare tunnel ---> mcp-proxy (Go facade)
                                              └─ launches + indexes MCP servers (fs/rg/sh/docs/memory/…)
                                              └─ synthesises a 2-tool catalog (search/fetch)
                                              └─ serves SSE + JSON-RPC on /mcp
                    ^
                    └ cloudflared keeps port 9090 reachable over TLS

Local dev (Codex CLI) ──> FastMCP bridge (`scripts/stelae_streamable_mcp.py`)
                               └─ runs in STDIO mode for Codex
                               └─ delegates all calls to the same mcp-proxy facade
```

### Why the catalog is trimmed

* The Cloudflare worker already rewrites the manifest to list only `search`/`fetch`.
* `mcp-proxy` now **filters the `initialize` and `tools/list` responses** to the same pair, regardless of how many downstream servers register tools. This keeps ChatGPT’s verifier happy while we retain the full fleet underneath.
* The proxy intercepts `tools/call search` and returns deterministic sample hits so the verifier can fetch follow-up content immediately. `fetch` is still delegated to the upstream fetch server.

## 2. Components

| Layer | Description |
| --- | --- |
| `mcp-proxy` (Go, `/home/gabri/apps/mcp-proxy`) | Aggregates all stdio MCP servers, exposes `/mcp` (SSE + JSON-RPC). Handles server discovery, tool filtering, and search stub responses. |
| MCP servers (fs, rg, sh, docs, memory, strata, fetch, …) | Spawned and supervised by `mcp-proxy`. They register their tools/prompts/resources, but the facade decides what is exposed. |
| `scripts/stelae_streamable_mcp.py` | FastMCP wrapper. Defaults to `STELAE_STREAMABLE_TRANSPORT=stdio` when invoked by Codex so local tooling has a hot MCP endpoint without extra startup latency. Static search hits are mirrored here for consistency. |
| `cloudflared` | Named tunnel publishing local port 9090 to `https://mcp.infotopology.xyz`. |
| `pm2` | Keeps `mcp-proxy`, the STDIO FastMCP bridge, `cloudflared`, and the watchdog running, and auto-starts them via `pm2 startup` + `pm2 save`. |
| Codex / ChatGPT clients | Both ultimately talk to the Go facade; Codex connects over STDIO via the FastMCP bridge, ChatGPT over HTTPS through Cloudflare. |

## 3. Runtime layout (pm2)

```bash
$ source ~/.nvm/nvm.sh && pm2 status
┌────┬──────────────┬─────────────┬─────────┬───────────┐
│ id │ name         │ mode        │ status  │ notes     │
├────┼──────────────┼─────────────┼─────────┼───────────┤
│ 0  │ mcp-proxy    │ fork        │ online  │ facade on :9090 │
│ 1  │ stelae-bridge│ fork        │ online  │ FastMCP STDIO bridge │
│ 2  │ cloudflared  │ fork        │ online  │ tunnel to mcp.infotopology.xyz │
│ 3  │ watchdog     │ fork        │ online  │ optional tunnel babysitter │
└────┴──────────────┴─────────────┴─────────┴───────────┘
```

`pm2 ls` should never show a `mcp-bridge` process anymore—the deprecated HTTP bridge was removed and its configs archived.

## 4. Key configs

* `config/proxy.json` – source of truth for downstream MCP servers. `mcp-proxy` reads this on boot.
* `Makefile` target `check-connector` – runs `dev/debug/check_connector.py`, hits the public endpoint, ensures the tool catalog is the trimmed pair, and archives probe logs.
* `C:\Users\gabri\.codex\config.toml` – Codex CLI entry; launches the STDIO bridge via WSL with `PYTHONPATH=/home/gabri/dev/stelae` so `scripts.*` resolves correctly.
* Cloudflare credentials under `~/.cloudflared/` – used by `cloudflared` pm2 process.

## 5. Health checks

### Local

```bash
# facade listening
ss -ltnp '"'"'( sport = :9090 )'"'"'

# SSE heartbeat (local)
curl -iN http://127.0.0.1:9090/mcp -H '"'"'Accept: text/event-stream'"'"' | head -5

# Run connector probe + assert catalog/search
make check-connector            # writes dev/logs/probe-<timestamp>.log
```

### Remote (via Cloudflare)

```bash
# manifest
curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq

# JSON-RPC initialize (public)
curl -s https://mcp.infotopology.xyz/mcp \
  -H '"'"'Content-Type: application/json'"'"' \
  --data '"'"'{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05"}}'"'"' | jq '"'"'.result.tools'"'"'

# Should print ["search", "fetch"]
```

## 6. Development workflow

1. **Make code changes** (Go proxy / search stub / docs). Run `gofmt` and unit tests:

   ```bash
   pushd /home/gabri/apps/mcp-proxy
   go test ./...
   popd
   ~/.venvs/stelae-bridge/bin/python -m pytest tests/test_streamable_mcp.py
   ```

2. **Redeploy facade** via the helper script:

   ```bash
   ./scripts/restart_stelae.sh
   ```

   This rebuilds the proxy binary, restarts pm2 processes, validates the tunnel, and prints a diagnostic `tools/list` sample.
3. **Validate** with `make check-connector`. Confirm the log shows only `search`/`fetch` and static hits.
4. **(Optional) Notify OpenAI** with the new session ID and initialize response once everything passes.

## 7. Troubleshooting

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `mcp-proxy` not listening on `:9090` | build failed or pm2 stopped | `./scripts/restart_stelae.sh` or `source ~/.nvm/nvm.sh && pm2 restart mcp-proxy` |
| `initialize` still lists dozens of tools | old facade binary still running | ensure Go proxy rebuilt (check timestamp), run restart script, rerun probe |
| `tools/call search` returns `{ "results": [] }` | running an old version; static hits missing | rebuild Go proxy (`facade_search.go`) and restart |
| Codex CLI reports “MCP client … request timed out” | STDIO bridge launched without proper env | confirm `config.toml` entry includes `PYTHONPATH=/home/gabri/dev/stelae` and `STELAE_STREAMABLE_TRANSPORT=stdio`; run `make check-connector` locally |
| Cloudflare 530 page | tunnel momentarily unhealthy | rerun `scripts/restart_stelae.sh` (ensures tunnel + pm2 state), or `source ~/.nvm/nvm.sh && pm2 restart cloudflared` |
| `make check-connector` fails with unexpected catalog | new upstream tools exposed | re-run after a minute; if persisting, inspect `logs/mcp-proxy.err.log` and ensure `collectTools` filters to the facade pair |
| `tools/call fetch` returns network errors | upstream site blocked or fetch server delay | retry, or inspect `logs/fetch.err.log` for HTTP errors |
| SSE drops quickly | Cloudflare idle timeout | facade sends keepalives every 15s; if missing, ensure Go proxy heartbeat loop is running |

## 8. Reference commands

```bash
# PM2 management
source ~/.nvm/nvm.sh
pm2 status
pm2 logs mcp-proxy --lines 150
pm2 restart cloudflared

# Re-run public probe & archive log
CONNECTOR_BASE=https://mcp.infotopology.xyz/mcp make check-connector

# Manual STDIO smoke test (inside WSL)
python - <<'"'"'PY'"'"'
import os, anyio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

params = StdioServerParameters(
    command='"'"'/home/gabri/.venvs/stelae-bridge/bin/python'"'"',
    args=['"'"'-m'"'"', '"'"'scripts.stelae_streamable_mcp'"'"'],
    env={
        '"'"'PYTHONPATH'"'"': '"'"'/home/gabri/dev/stelae'"'"',
        '"'"'STELAE_PROXY_BASE'"'"': '"'"'http://127.0.0.1:9090'"'"',
        '"'"'STELAE_STREAMABLE_TRANSPORT'"'"': '"'"'stdio'"'"',
        '"'"'PATH'"'"': os.environ['"'"'PATH'"'"'],
    },
    cwd='"'"'/home/gabri/dev/stelae'"'"',
)
async def main():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(init.serverInfo)
            tools = await session.list_tools()
            print([t.name for t in tools.tools])
anyio.run(main)
PY
```

This spec reflects the current production arrangement: a single Go facade, one STDIO FastMCP bridge, and a Cloudflare tunnel. The deprecated HTTP bridge has been archived, and all validation tooling expects the trimmed search/fetch catalog.
