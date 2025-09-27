# final push — make every tool show up in `tools/list`

> goal: fs, rg, sh, docs, mem, strata, fetch, github all appear at `tools/list` and are callable via `/mcp`.

## 0) single entrypoint + named tunnel

- public endpoint: `https://mcp.infotopology.xyz/mcp` (no bridge)
- proxy listens on **:9090**
- cloudflared must run **named tunnel**: `tunnel run stelae` (quick-tunnel will cause 530/HTML)

check:

```bash
pm2 describe cloudflared | egrep 'script args|name'
# expect: tunnel run stelae

# validate ingress → origin 127.0.0.1:9090
cloudflared tunnel ingress validate
````

## 1) servers actually registered?

```bash
pm2 logs mcp-proxy --lines 200 | grep -E 'Handling requests at|sse server listening'
# expect: /sh/ /rg/ /docs/ /mem/ /strata/ /fetch/ (and /fs/ if enabled)
```

## 2) local façade sanity

```bash
# HEAD should be 200
curl -sI http://127.0.0.1:9090/mcp | sed -n '1,8p'

# initialize
curl -s http://127.0.0.1:9090/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq .

# tools list (local)
curl -s http://127.0.0.1:9090/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,200p'
```

## 3) public sanity

```bash
# manifest should be 200 application/json
curl -si https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | sed -n '1,12p'

# tools list (public)
curl -s https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,200p'
```

*if you get `jq: parse error…`, it’s an HTML error page → check cloudflared is using `tunnel run stelae` and that ingress maps your hostname to `http://127.0.0.1:9090`.*

## 4) quick smoke tests (via /mcp)

```bash
# fetch (should always work)
curl -s https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"f","method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com","raw":true}}}' | jq '.result | keys'

# grep
curl -s https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"rg","method":"tools/call","params":{"name":"grep","arguments":{"pattern":"Stelae","paths":["/home/gabri/dev/stelae"],"max_count":2,"recursive":true}}}' | jq '.result | keys'

# shell (allowlisted)
curl -s https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"sh","method":"tools/call","params":{"name":"execute_command","arguments":{"cmd":"git","args":["status","--porcelain"]}}}' | jq '.result | keys'
```

## 5) common “last mile” gotchas

- **Only github + fetch show:** the others *are* registering; your connector might filter by capability. Confirm via `tools/list` curl (public).
- **530/520 on public:** pm2 is running `tunnel --url …` (quick tunnel). Fix: `pm2 restart cloudflared --update-env -- tunnel run stelae`.
- **Empty tools list:** restart proxy once; if still empty, `pm2 logs mcp-proxy` and look for registration lines.
- **401 when hitting server subpaths:** expected. Only call via `/mcp`—facade sets internal bypass header.

## 6) acceptance

- `tools/list` (public) shows fs, rg, sh, docs, mem, strata, fetch, github
- at least two tool calls succeed (e.g., `fetch` + `grep` or `execute_command`)

---

### helper: restart stack

Use the script:

```bash
bash stelae/scripts/restart_stelae.sh
# add --no-cloudflared for local-only
# add --keep-pm2 to avoid killing/reloading everything
```
