# path: stelae/scripts/restart_stelae.sh
#!/usr/bin/env bash
set -euo pipefail

# --- paths & config -----------------------------------------------------------
HOME_DIR="${HOME}"
STELAE_DIR="${STELAE_DIR:-$HOME_DIR/dev/stelae}"
APPS_DIR="${APPS_DIR:-$HOME_DIR/apps}"

PROXY_DIR="${APPS_DIR}/mcp-proxy"
PROXY_BIN="${PROXY_BIN:-$PROXY_DIR/build/mcp-proxy}"
PROXY_TEMPLATE="${STELAE_DIR}/config/proxy.template.json"
PROXY_JSON="${STELAE_DIR}/config/proxy.json"
RENDERER="${STELAE_DIR}/scripts/render_proxy_config.py"
ECOSYSTEM="${STELAE_DIR}/ecosystem.config.js"

PROXY_PORT="${PROXY_PORT:-9090}"                   # proxy listens here

# cloudflared (named tunnel w/ config)
CLOUDFLARED_BIN="${CLOUDFLARED:-$HOME_DIR/.nvm/versions/node/v22.19.0/bin/cloudflared}"
CF_TUNNEL_NAME="${CF_TUNNEL_NAME:-stelae}"
CF_DIR="$HOME_DIR/.cloudflared"
CF_CONF="$CF_DIR/config.yml"

# public URL for probes
PUBLIC_BASE_URL="$(grep -E '^PUBLIC_BASE_URL=' "$STELAE_DIR/.env" 2>/dev/null | sed 's/^[^=]*=//')"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://mcp.infotopology.xyz}"

# readiness thresholds
MIN_TOOL_COUNT="${MIN_TOOL_COUNT:-12}"             # “warm enough” before exposing
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-45}"

# options ----------------------------------------------------------------------
START_CLOUDFLARED=1
KEEP_PM2=0
for arg in "$@"; do
  case "$arg" in
    --no-cloudflared) START_CLOUDFLARED=0;;
    --keep-pm2) KEEP_PM2=1;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [options]
  --no-cloudflared   Skip starting cloudflared via pm2
  --keep-pm2         Do not 'pm2 kill'; just (re)start managed apps

Env overrides:
  PROXY_PORT        (default 9090)
  MIN_TOOL_COUNT    (default 12)
  READY_TIMEOUT_SEC (default 45)
EOF
      exit 0
    ;;
  esac
done

# helpers ----------------------------------------------------------------------
log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; }
require() { command -v "$1" >/dev/null 2>&1 || { err "missing command: $1"; exit 1; }; }

wait_port() {
  local port="$1" label="$2" tries=60
  for _ in $(seq 1 $tries); do
    if ss -ltn "( sport = :$port )" | grep -q ":$port"; then
      log "$label is listening on :$port"
      return 0
    fi
    sleep 0.25
  done
  return 1
}

local_tool_count() {
  curl -s "http://127.0.0.1:${PROXY_PORT}/mcp" -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
  | jq -r 'try (.result.tools|length) // 0' 2>/dev/null || echo 0
}

wait_tools_ready() {
  log "Waiting for tools to register (target >= ${MIN_TOOL_COUNT}, timeout ${READY_TIMEOUT_SEC}s)…"
  local start ts count=0
  start=$(date +%s)
  while :; do
    count="$(local_tool_count)"
    if [ "${count:-0}" -ge "$MIN_TOOL_COUNT" ]; then
      log "Tool catalog ready: ${count} tools."
      return 0
    fi
    ts=$(date +%s)
    if [ $((ts - start)) -ge "$READY_TIMEOUT_SEC" ]; then
      warn "Timed out at ${count} tools; continuing (public may briefly see fewer tools)."
      return 0
    fi
    sleep 1
  done
}

ensure_cloudflared_ingress() {
  mkdir -p "$CF_DIR"
  local tuuid
  tuuid="$(cloudflared tunnel list 2>/dev/null | awk -v n="$CF_TUNNEL_NAME" '$2==n{print $1}' | head -n1 || true)"
  if [[ -z "$tuuid" ]]; then
    warn "Tunnel '$CF_TUNNEL_NAME' not found; create it: cloudflared tunnel create $CF_TUNNEL_NAME"
    return 0
  fi
  if [[ ! -f "$CF_CONF" ]]; then
    log "Writing $CF_CONF for tunnel $CF_TUNNEL_NAME → 127.0.0.1:$PROXY_PORT"
    cat > "$CF_CONF" <<EOF
tunnel: ${tuuid}
credentials-file: ${CF_DIR}/${tuuid}.json
originRequest:
  http2Origin: true
  disableChunkedEncoding: true
  connectTimeout: 10s
  keepAliveTimeout: 65s
  tcpKeepAlive: 60s
ingress:
  - hostname: mcp.infotopology.xyz
    service: http://127.0.0.1:${PROXY_PORT}
  - service: http_status:404
EOF
  fi
  cloudflared tunnel ingress validate || warn "cloudflared ingress validate returned non-zero"
  cloudflared tunnel route dns "$CF_TUNNEL_NAME" mcp.infotopology.xyz >/dev/null 2>&1 || true
}

show_public_jsonrpc_once() {
  local url="$1"
  local hdrs body status ctype cfray rc=1
  hdrs="$(mktemp)"
  body="$(curl -sk -D "$hdrs" \
               -H 'Content-Type: application/json' \
               -H 'Accept: application/json' \
               -H 'User-Agent: stelae-health/1.0' \
               --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
               "$url" || true)"
  status="$(sed -n '1p' "$hdrs")"
  ctype="$(grep -i '^content-type:' "$hdrs" | head -1 | cut -d' ' -f2-)"
  cfray="$(grep -i '^cf-ray:' "$hdrs" | head -1 | cut -d' ' -f2-)"
  echo "$status"
  echo "content-type: ${ctype:-<none>}"
  [ -n "$cfray" ] && echo "cf-ray: $cfray"
  if echo "${ctype,,}" | grep -q 'application/json'; then
    echo "$body" | jq -C '.result | {toolCount: (try .tools|length // 0), sample: (try .tools[0:5][]?.name // [])}' || echo "$body" | head -c 200
    rc=0
  else
    echo "--- body preview (non-JSON) ---"
    echo "$body" | head -c 400; echo
    rc=1
  fi
  rm -f "$hdrs"
  return $rc
}

show_public_jsonrpc_retry() {
  local url="$1" tries=3
  for i in $(seq 1 $tries); do
    if show_public_jsonrpc_once "$url"; then return 0; fi
    echo "--- retry $i/$tries ---"
    sleep 1
  done
  return 1
}

# prereqs ----------------------------------------------------------------------
require jq
require python3
require ss
if [ -s "$HOME_DIR/.nvm/nvm.sh" ]; then . "$HOME_DIR/.nvm/nvm.sh"; fi
require pm2
mkdir -p "$STELAE_DIR/logs"

# stop / clean -----------------------------------------------------------------
if [ "$KEEP_PM2" -eq 0 ]; then
  log "Killing pm2 (all processes)…"
  pm2 kill || true
  rm -f "$HOME_DIR/.pm2/pm2.pid" || true
else
  warn "--keep-pm2 set: will not kill pm2, only restart known apps"
fi

log "Killing stray listeners on :$PROXY_PORT (if any)…"
mapfile -t PIDS < <(ss -ltnp "( sport = :$PROXY_PORT )" | awk -F',' '/pid=/{print $2}' | sed 's/pid=//' | awk '{print $1}' | sort -u)
if [ "${#PIDS[@]}" -gt 0 ]; then for pid in "${PIDS[@]}"; do kill -9 "$pid" 2>/dev/null || true; done; fi

# render proxy config ----------------------------------------------------------
log "Rendering proxy config → $PROXY_JSON"
python3 "$RENDERER" --template "$PROXY_TEMPLATE" --output "$PROXY_JSON" --env-file "$STELAE_DIR/.env" --fallback-env "$STELAE_DIR/.env.example"
python3 - <<'PY' "$PROXY_JSON"
import json,sys; json.load(open(sys.argv[1]))
PY

# start local proxy + servers --------------------------------------------------
log "Starting mcp-proxy via pm2"
pm2 start "$ECOSYSTEM" --only mcp-proxy 2>/dev/null || pm2 restart mcp-proxy --update-env
for svc in strata docy memory shell; do
  pm2 start "$ECOSYSTEM" --only "$svc" 2>/dev/null || pm2 restart "$svc" --update-env 2>/dev/null || true
done
pm2 save || true

wait_port "$PROXY_PORT" "mcp-proxy" || { err "proxy didn’t bind :$PROXY_PORT"; pm2 logs mcp-proxy --lines 120; exit 2; }

# local readiness (before exposing) -------------------------------------------
log "Local probe: HEAD http://127.0.0.1:${PROXY_PORT}/mcp"
curl -sI "http://127.0.0.1:${PROXY_PORT}/mcp" | sed -n '1,10p' || true

log "Local probe: initialize (JSON-RPC)"
curl -s "http://127.0.0.1:${PROXY_PORT}/mcp" -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq -C '.' || true

wait_tools_ready

log "Local probe: tools/list → names (first 40)"
curl -s "http://127.0.0.1:${PROXY_PORT}/mcp" -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,40p' || true

# start cloudflared only when local is warm -----------------------------------
if [ "$START_CLOUDFLARED" -eq 1 ]; then
  require "$CLOUDFLARED_BIN"
  ensure_cloudflared_ingress
  log "Ensuring cloudflared pm2 process (flags first)…"
  if ! pm2 describe cloudflared >/dev/null 2>&1; then
    pm2 start "$CLOUDFLARED_BIN" --name cloudflared -- --no-chunked-encoding --config "${CF_CONF}" tunnel run "${CF_TUNNEL_NAME}"
  else
    pm2 restart cloudflared --update-env -- --no-chunked-encoding --config "${CF_CONF}" tunnel run "${CF_TUNNEL_NAME}"
  fi
  pm2 save || true
else
  warn "Skipping cloudflared (--no-cloudflared)."
fi

# public probes (best-effort; tolerate CF 530 blips) ---------------------------
if [ "$START_CLOUDFLARED" -eq 1 ] && [ -n "$PUBLIC_BASE_URL" ]; then
  log "Public probe: manifest"
  curl -skI "${PUBLIC_BASE_URL}/.well-known/mcp/manifest.json" | sed -n '1,12p' || true

  log "Public probe: tools/list (JSON-RPC, retry + diagnostics)"
  show_public_jsonrpc_retry "${PUBLIC_BASE_URL}/mcp" || true
fi

log "Done. For issues, check: 'pm2 logs mcp-proxy --lines 150' and 'pm2 logs cloudflared --lines 80'."
