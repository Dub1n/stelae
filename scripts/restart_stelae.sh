#   RESTART STELAE
# - kills pm2 + stray listeners on 9090/9092,
# - re-renders config/proxy.json from your template,
# - (re)builds the bridge venv (optional flag),
# - exports BRIDGE_PY for pm2 (so the bridge uses the venv),
# - restarts all pm2 apps (bridge → proxy → others),
# - (re)starts cloudflared under pm2,
# - sanity-probes local and public endpoints.
#
#   flags:
# --recreate-bridge-venv wipe & rebuild the bridge venv
# --no-cloudflared skip starting cloudflared (if you’re testing local-only)
# --keep-pm2 don’t pm2 kill (just restart known apps)

#!/usr/bin/env bash
set -euo pipefail

### -------- config (paths) --------
HOME_DIR="${HOME}"
STELAE_DIR="${STELAE_DIR:-$HOME_DIR/dev/stelae}"
APPS_DIR="${APPS_DIR:-$HOME_DIR/apps}"
PROXY_DIR="${APPS_DIR}/mcp-proxy"
PROXY_BIN="${PROXY_BIN:-$PROXY_DIR/build/mcp-proxy}"
PROXY_TEMPLATE="${STELAE_DIR}/config/proxy.template.json"
PROXY_JSON="${STELAE_DIR}/config/proxy.json"
RENDERER="${STELAE_DIR}/scripts/render_proxy_config.py"
ECOSYSTEM="${STELAE_DIR}/ecosystem.config.js"
BRIDGE_VENV="${HOME_DIR}/.venvs/stelae-bridge"
BRIDGE_PY_DEFAULT="${BRIDGE_VENV}/bin/python"
REQUIREMENTS="${STELAE_DIR}/bridge/requirements.txt"
CLOUDFLARE_CMD="${CLOUDFLARED:-cloudflared} tunnel run stelae"

# ports: proxy on 9092, bridge on 9090
BRIDGE_PORT="${BRIDGE_PORT:-9090}"
PROXY_PORT="${PROXY_PORT:-9092}"

# public URL (for probes)
PUBLIC_BASE_URL="$(grep -E '^PUBLIC_BASE_URL=' "$STELAE_DIR/.env" 2>/dev/null | sed 's/^[^=]*=//')"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://mcp.infotopology.xyz}"

### -------- options --------
RECREATE_VENV=0
START_CLOUDFLARED=1
KEEP_PM2=0
for arg in "$@"; do
  case "$arg" in
    --recreate-bridge-venv) RECREATE_VENV=1;;
    --no-cloudflared) START_CLOUDFLARED=0;;
    --keep-pm2) KEEP_PM2=1;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --recreate-bridge-venv   Wipe and rebuild ~/.venvs/stelae-bridge
  --no-cloudflared         Skip starting cloudflared via pm2
  --keep-pm2               Do not 'pm2 kill'; just (re)start managed apps
EOF
      exit 0
    ;;
  esac
done

### -------- helpers --------
log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; }

require() { command -v "$1" >/dev/null 2>&1 || { err "missing command: $1"; exit 1; }; }

curl_json() {
  curl -s --max-time 10 "$@" || true
}

wait_port() {
  local port="$1" label="$2" tries=50
  for _ in $(seq 1 $tries); do
    if ss -ltn "( sport = :$port )" | grep -q ":$port"; then
      log "$label is listening on :$port"
      return 0
    fi
    sleep 0.2
  done
  return 1
}

### -------- env prep --------
require bash
require jq
require python3
require ss
# pm2 lives under nvm; source it
if [ -s "$HOME_DIR/.nvm/nvm.sh" ]; then
  # shellcheck source=/dev/null
  . "$HOME_DIR/.nvm/nvm.sh"
fi
require pm2

mkdir -p "$STELAE_DIR/logs"

### -------- stop everything --------
if [ "$KEEP_PM2" -eq 0 ]; then
  log "Killing pm2 (all processes)…"
  pm2 kill || true
  rm -f "$HOME_DIR/.pm2/pm2.pid" || true
else
  warn "--keep-pm2 set: will not kill pm2, only restart known apps"
fi

log "Killing stray listeners on :$BRIDGE_PORT and :$PROXY_PORT (if any)…"
for p in "$BRIDGE_PORT" "$PROXY_PORT"; do
  mapfile -t PIDS < <(ss -ltnp "( sport = :$p )" | awk -F',' '/pid=/ {print $2}' | sed 's/pid=//' | awk '{print $1}' | sort -u)
  if [ "${#PIDS[@]}" -gt 0 ]; then
    for pid in "${PIDS[@]}"; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi
done

### -------- (re)render proxy config --------
log "Rendering proxy config → $PROXY_JSON"
if [ ! -f "$PROXY_TEMPLATE" ]; then
  err "Template missing: $PROXY_TEMPLATE"
  exit 1
fi
python3 "$RENDERER" --template "$PROXY_TEMPLATE" --output "$PROXY_JSON" --env-file "$STELAE_DIR/.env" || {
  err "proxy render failed"; exit 1; }

### -------- bridge venv --------
BRIDGE_PY="$BRIDGE_PY_DEFAULT"
if [ "$RECREATE_VENV" -eq 1 ]; then
  log "Recreating bridge venv at $BRIDGE_VENV"
  rm -rf "$BRIDGE_VENV"
fi
if [ ! -x "$BRIDGE_PY" ]; then
  log "Creating bridge venv at $BRIDGE_VENV"
  python3 -m venv "$BRIDGE_VENV"
fi
log "Installing bridge deps into venv"
"$BRIDGE_PY" -m pip install --upgrade pip >/dev/null
"$BRIDGE_PY" -m pip install -r "$REQUIREMENTS" >/dev/null

### -------- (re)start core via pm2 --------
if [ ! -f "$ECOSYSTEM" ]; then
  err "Missing ecosystem file: $ECOSYSTEM"
  exit 1
fi

log "Starting mcp-proxy (on :$PROXY_PORT) and mcp-bridge (on :$BRIDGE_PORT) via pm2"
# export BRIDGE_PY so ecosystem uses the venv python
export BRIDGE_PY

# start only what we need, in order
pm2 start "$ECOSYSTEM" --only mcp-proxy || pm2 restart mcp-proxy --update-env
pm2 start "$ECOSYSTEM" --only mcp-bridge || pm2 restart mcp-bridge --update-env

# then the rest (best-effort)
for svc in strata docy memory shell 1mcp; do
  pm2 start "$ECOSYSTEM" --only "$svc" 2>/dev/null || pm2 restart "$svc" --update-env 2>/dev/null || true
done

pm2 save || true

### -------- wait for listeners --------
wait_port "$PROXY_PORT" "mcp-proxy" || { err "proxy didn’t bind :$PROXY_PORT"; pm2 logs mcp-proxy --lines 80; exit 2; }
wait_port "$BRIDGE_PORT" "mcp-bridge" || { err "bridge didn’t bind :$BRIDGE_PORT"; pm2 logs mcp-bridge --lines 120; exit 2; }

### -------- local probes --------
log "Local probe: HEAD http://127.0.0.1:${BRIDGE_PORT}/mcp"
if ! curl -sI "http://127.0.0.1:${BRIDGE_PORT}/mcp" | head -n 1 | grep -q "200"; then
  warn "Bridge HEAD /mcp didn’t return 200; showing recent logs"
  pm2 logs mcp-bridge --lines 120 || true
fi

log "Local probe: GET  http://127.0.0.1:${BRIDGE_PORT}/healthz"
curl_json "http://127.0.0.1:${BRIDGE_PORT}/healthz" | jq -C '.' || true

log "Local probe: GET  http://127.0.0.1:${BRIDGE_PORT}/version"
curl_json "http://127.0.0.1:${BRIDGE_PORT}/version" | jq -C '.' || true

log "Local probe: manifest from proxy http://127.0.0.1:${PROXY_PORT}/.well-known/mcp/manifest.json"
curl_json "http://127.0.0.1:${PROXY_PORT}/.well-known/mcp/manifest.json" | jq '{tools: (.tools | map(.name))}' || true

### -------- start cloudflared (optional) --------
if [ "$START_CLOUDFLARED" -eq 1 ]; then
  log "Ensuring cloudflared tunnel (pm2: cloudflared)…"
  if ! pm2 describe cloudflared >/dev/null 2>&1; then
    pm2 start "$CLOUDFLARE_CMD" --name cloudflared || true
  else
    pm2 restart cloudflared || true
  fi
  pm2 save || true
else
  warn "Skipping cloudflared (--no-cloudflared)."
fi

### -------- public probes (if cloudflared) --------
if [ "$START_CLOUDFLARED" -eq 1 ] && [ -n "$PUBLIC_BASE_URL" ]; then
  log "Public probe: HEAD ${PUBLIC_BASE_URL}/mcp"
  curl -skI "${PUBLIC_BASE_URL}/mcp" | sed -n '1,10p' || true

  log "Public probe: POST initialize → expect 202"
  curl -skX POST "${PUBLIC_BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{"experimental.streamJsonRpc":true}}}' \
    -i | sed -n '1,12p' || true

  log "Public probe: GET  ${PUBLIC_BASE_URL}/healthz"
  curl_json "${PUBLIC_BASE_URL}/healthz" | jq -C '.' || true

  log "Public probe: GET  ${PUBLIC_BASE_URL}/version"
  curl_json "${PUBLIC_BASE_URL}/version" | jq -C '.' || true

  log "Public probe: manifest (via bridge passthrough)"
  curl_json "${PUBLIC_BASE_URL}/.well-known/mcp/manifest.json" | jq '{ok:true, tools: (.tools | map(.name))}' || true
fi

log "All done. If anything looks off: 'pm2 logs mcp-bridge --lines 200' and 'pm2 logs mcp-proxy --lines 120'."
