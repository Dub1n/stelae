---
updated: 2025-09-29-14:48
---

# stelae MCP stack – architecture spec

## 1. High-level flow

The goal is to present a **single MCP endpoint** (`https://mcp.infotopology.xyz/mcp`) that both local tools (Codex CLI/VS Code) and remote ChatGPT Connectors can rely on. Internally we compose many MCP-capable services, and the facade now exposes the complete downstream tool catalog with explicit annotation overrides where required.

```diagram
ChatGPT / Codex ---> Cloudflare tunnel ---> mcp-proxy (Go facade)
                                              └─ launches + indexes MCP servers (fs/rg/sh/docs/memory/…)
                                              └─ merges downstream descriptors + override hints
                                              └─ serves SSE + JSON-RPC on /mcp
                    ^
                    └ cloudflared keeps port 9090 reachable over TLS

Local dev (Codex CLI) ──> FastMCP bridge (`scripts/stelae_streamable_mcp.py`)
                               └─ runs in STDIO mode for Codex
                               └─ delegates all calls to the same mcp-proxy facade
```

### Catalog exposure & annotations

* Both `initialize` and `tools/list` now mirror the full downstream tool inventory so Connectors and local agents see identical capabilities.
* The Cloudflare worker still normalises manifest metadata (endpoint URL, server slug) but leaves the tool list intact.
* Tool behaviour hints (`readOnlyHint`, `openWorldHint`, etc.) default to `false` unless supplied by an upstream server or via `config/tool_overrides.json` (per-server entries and a `master` section that supports specific names or `"*"`). Overrides apply consistently to the manifest, `initialize`, and `tools/list` responses.

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

* `config/proxy.json` – rendered facade config (servers, manifest metadata, override file path).
* `config/tool_overrides.json` – optional per-server and `master` annotation overrides merged on proxy startup.
* `Makefile` target `check-connector` – runs `dev/debug/check_connector.py`, hits the public endpoint, and records the published tool catalog (verify overrides appear as expected).
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

# Inspect the tool list and ensure expected overrides (e.g. `read_file` ⇒ `readOnlyHint: true`).
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
3. **Validate** with `make check-connector`. Confirm the log reflects the full downstream catalog and that override hints (e.g. `readOnlyHint` for `read_file`) are present.
4. **(Optional) Notify OpenAI** with the new session ID and initialize response once everything passes.

## 7. Troubleshooting

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `mcp-proxy` not listening on `:9090` | build failed or pm2 stopped | `./scripts/restart_stelae.sh` or `source ~/.nvm/nvm.sh && pm2 restart mcp-proxy` |
| Override hints missing from manifest | override file not loaded or stale | confirm `config/tool_overrides.json` is valid JSON, rerun `make render-proxy`, then `scripts/restart_stelae.sh --full` |
| `tools/call search` returns `{ "results": [] }` | running an old version; static hits missing | rebuild Go proxy (`facade_search.go`) and restart |
| Codex CLI reports “MCP client … request timed out” | STDIO bridge launched without proper env | confirm `config.toml` entry includes `PYTHONPATH=/home/gabri/dev/stelae` and `STELAE_STREAMABLE_TRANSPORT=stdio`; run `make check-connector` locally |
| Cloudflare 530 page | tunnel momentarily unhealthy | rerun `scripts/restart_stelae.sh` (ensures tunnel + pm2 state), or `source ~/.nvm/nvm.sh && pm2 restart cloudflared` |
| `make check-connector` flags unexpected catalog | new upstream tools exposed or overrides missing | inspect `logs/mcp-proxy.err.log` and confirm `config/tool_overrides.json` is up to date, then rerun the restart script |
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

This spec reflects the current production arrangement: a single Go facade, one STDIO FastMCP bridge, and a Cloudflare tunnel. The deprecated HTTP bridge has been archived, and validation tooling now inspects the full downstream catalog with annotation overrides applied.

Response Headers:
access-control-allow-credentials
true
access-control-allow-origin
*
cf-cache-status
DYNAMIC
cf-ray
986696dcc9312aca-LHR
content-length
16
content-type
application/json
cross-origin-opener-policy
same-origin-allow-popups
date
Sun, 28 Sep 2025 22:13:39 GMT
nel
{"success_fraction":0.01,"report_to":"cf-nel","max_age":604800}
permissions-policy
interest-cohort=()
referrer-policy
strict-origin-when-cross-origin
report-to
{"endpoints":[{"url":"https:\/\/a.nel.cloudflare.com\/report\/v4?s=P5u15tEGfuMOrANAs8Jr%2FmoZr8uHfxGN1XaZeL2RTJIIj8dd9NNZJEJmGCuy6sFuSSRqMTIm7qdA%2BrJ3zzO89KCPLZiPsW4tjapayrFbmewgb5pSYQNsrJIS%2Bv12vT25"}],"group":"cf-nel","max_age":604800}
server
cloudflare
set-cookie
GCLB="df328852bd8a8dc5"; Max-Age=1; Path=/; HttpOnly
strict-transport-security
max-age=31536000; includeSubDomains; preload
via
1.1 google
x-content-type-options
nosniff
x-frame-options
SAMEORIGIN
x-response-time
0 ms
x-robots-tag
nofollow

Request headers:
:authority
ab.chatgpt.com
:method
POST
:path
/v1/rgstr?k=client-nb0qtYlZuy2tCMN5s5ncnuIBCJncjRViT0IzFm7GqST&st=javascript-client&sv=3.17.0&t=1759097619662&sid=bc8f532b-1ea0-4384-a90a-e3dc03042b51&ec=2&gz=1
:scheme
https
accept
*/*
accept-encoding
gzip, deflate, br, zstd
accept-language
en-GB,en-US;q=0.9,en;q=0.8
content-length
958
origin
https://chatgpt.com
priority
u=1, i
referer
https://chatgpt.com/
sec-ch-ua
"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"
sec-ch-ua-mobile
?0
sec-ch-ua-platform
"Windows"
sec-fetch-dest
empty
sec-fetch-mode
cors
sec-fetch-site
same-site
user-agent
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36

Query string parameters:
k=client-nb0qtYlZuy2tCMN5s5ncnuIBCJncjRViT0IzFm7GqST&st=javascript-client&sv=3.17.0&t=1759097619662&sid=bc8f532b-1ea0-4384-a90a-e3dc03042b51&ec=2&gz=1

Request payload:

íMoÛFÿ0§ )~_¹ÔÜÔ°¸µ(b¹R[-wÝ¥bÙÐ/¢Ýõ¡IöPBQÔ¾wæpÂh(~{8^¾#BÚ£Y[ìQx×K=(
ñûl
ÅxáÖ'»5þxQíï¾/ª_Óõ§V^ØÆ¡T!c?öýZ{×£²Xä¡ú^^º¨Q{(àíë)êIÂ@òqN+Ï_¼¸e¢õâÝÍ"ð=ÿÕâ$~µ¸Kâ¾çxÕ93ËUzQ²xqþÓÍå³àl·H·òåâÍFÉAì{ãgqM¢Ø$±ÉÚÈÎVÝs"J³ï­G½àÀg©¶º'KVCq~¢'ïÆºyFÐ,¦Ä'aMì ü&
ÓeO¬À¨ Ù¶O¸l[¬K&À
ÑåÓï²ÂF*|TY#Kò9ikÝr0åqÂ5NcRÖ²#ìÉa-)#ü(«3ñi$­²¶÷¨¬G'ÅÀùÁ.)áVÂ}ýÔ¿³µ¶-¼ÅêDH±ïä ßH¹e814ÍhP¹1fgYãVYEÜbÚ4qP×Y
¬qÇ(Õ_¡
©ø7Åø·Fêà<¾ç§bÇÝèîfc¼¨aRÀáàÀð&;Ð¡!51Ä§R4¬¢<Ló0MW98ÐE:4¨&¤ °>5¶z8 É¤2pc+â¶ëÓ;Ûäcv0Ãé]Ïeæê10N8PIi´Q¤¿ü"Ç[3¶flý±Õ¢@ET×ëó3ÑH{R×Û©WÇ'¹BÖºÞ~@¥­¶Ä½Ôãt0Pé*÷óUæAPHôxîõ#p_ÊV°{¬áQ_É,è"Ûa}òçé*ÍÄ+C*EMÔþtZ¹ìnöÑÃ,D§ãI'aödÃ£R(Ìimucz],tCLÛ®¥5e^öfjÎÔ©ù=?ü$N£ç=*»^ZVô|ÐnbW¼V3¬fXÍ+Þ³+Þ´ÄØló Î<Í3pÆ[ ~Bß_ zxn;Òïß?>+ýÊ¶ÈRÏ?9¹ü;ÙMëK9³íúÓ¨mQRÑ¬YEaåH|7²Ø%¹O\jêG~V«k¯Ý¾W|zÏÃ/ã×

* Setting `enabled: false` on a server, on a specific tool, or via the `master` section removes the tool from manifest/initialize/tools.list responses (upstream servers still load, but clients no longer see those entries).