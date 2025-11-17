#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
HOME_DIR="${HOME}"
DEFAULT_CONFIG_HOME="${HOME_DIR}/.config/stelae"
INITIAL_CONFIG_HOME="${STELAE_CONFIG_HOME:-$DEFAULT_CONFIG_HOME}"
ENV_FILE_CANDIDATE="${STELAE_ENV_FILE:-${INITIAL_CONFIG_HOME}/.env}"
REPO_ENV_FILE="${REPO_ROOT}/.env"
ENV_SOURCED=""

if [ -f "$ENV_FILE_CANDIDATE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE_CANDIDATE"
  set +a
  ENV_SOURCED="$ENV_FILE_CANDIDATE"
elif [ -f "$REPO_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$REPO_ENV_FILE"
  set +a
  ENV_SOURCED="$REPO_ENV_FILE"
else
  err "Env file not found (looked for ${ENV_FILE_CANDIDATE} and ${REPO_ENV_FILE}); run scripts/setup_env.py first."
  exit 1
fi

if [ -z "${STELAE_CONFIG_HOME:-}" ]; then
  err "Missing STELAE_CONFIG_HOME in ${ENV_SOURCED}; run scripts/setup_env.py."
  exit 1
fi
if [ -z "${STELAE_STATE_HOME:-}" ]; then
  err "Missing STELAE_STATE_HOME in ${ENV_SOURCED}; run scripts/setup_env.py."
  exit 1
fi
STELAE_ENV_FILE="${STELAE_ENV_FILE:-${STELAE_CONFIG_HOME}/.env}"
export STELAE_ENV_FILE

SCRIPT_START=$(date +%s)

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log()  { printf '\033[1;34m==>\033[0m [%s] %s\n' "$(timestamp)" "$*"; }
warn() { printf '\033[1;33m!!\033[0m [%s] %s\n' "$(timestamp)" "$*"; }
err()  { printf '\033[1;31mxx\033[0m [%s] %s\n' "$(timestamp)" "$*" >&2; }
require() { command -v "$1" >/dev/null 2>&1 || { err "missing command: $1"; exit 1; }; }

on_exit() {
  local status=$?
  local end
  end=$(date +%s)
  local elapsed=$((end - SCRIPT_START))
  if [ $status -eq 0 ]; then
    log "Restart script completed in ${elapsed}s."
  else
    err "Restart script exited with status $status after ${elapsed}s."
  fi
}
trap on_exit EXIT

if [ -n "$ENV_SOURCED" ]; then
  log "Loaded environment variables from $ENV_SOURCED"
fi

# --- paths & config -----------------------------------------------------------
case "$STELAE_CONFIG_HOME" in
  /*) ;;
  *) err "STELAE_CONFIG_HOME must be absolute (got $STELAE_CONFIG_HOME)"; exit 1;;
esac
case "$STELAE_STATE_HOME" in
  "$STELAE_CONFIG_HOME"/*) ;;
  *) err "STELAE_STATE_HOME must live under $STELAE_CONFIG_HOME (got $STELAE_STATE_HOME)"; exit 1;;
esac
STELAE_DIR="${STELAE_DIR:-$REPO_ROOT}"
APPS_DIR="${APPS_DIR:-$HOME_DIR/apps}"
STELAE_STATE_HOME="${STELAE_STATE_HOME:-$STELAE_CONFIG_HOME/.state}"
mkdir -p "$STELAE_STATE_HOME"

PROXY_DIR="${APPS_DIR}/mcp-proxy"
PROXY_BIN="${PROXY_BIN:-$PROXY_DIR/build/mcp-proxy}"
PROXY_TEMPLATE="${STELAE_DIR}/config/proxy.template.json"
PROXY_JSON="${PROXY_CONFIG:-$STELAE_STATE_HOME/proxy.json}"
RENDERER="${STELAE_DIR}/scripts/render_proxy_config.py"
ECOSYSTEM="${STELAE_DIR}/ecosystem.config.js"
PYTHON_BIN="${PYTHON:-$HOME_DIR/.venvs/stelae-bridge/bin/python}"

PROXY_PORT="${PROXY_PORT:-9090}"                   # proxy listens here
export PROXY_CONFIG="$PROXY_JSON"

REQUIRED_ENV_VARS=("TOOL_OVERRIDES_PATH" "TOOL_SCHEMA_STATUS_PATH" "STELAE_CUSTOM_TOOLS_CONFIG" "STELAE_DISCOVERY_PATH" "INTENDED_CATALOG_PATH" "LIVE_CATALOG_PATH")
for var in "${REQUIRED_ENV_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    err "Missing required env ${var}; set it in ${ENV_SOURCED}."
    exit 1
  fi
done
log "Paths: config_home=${STELAE_CONFIG_HOME} state_home=${STELAE_STATE_HOME} env_file=${STELAE_ENV_FILE}"
log "Runtime: proxy_config=${PROXY_JSON} overrides=${TOOL_OVERRIDES_PATH} schema_status=${TOOL_SCHEMA_STATUS_PATH} discovery=${STELAE_DISCOVERY_PATH}"
log "Catalog: intended=${INTENDED_CATALOG_PATH} live=${LIVE_CATALOG_PATH}"

# cloudflared (named tunnel w/ config)
CLOUDFLARED_BIN="${CLOUDFLARED:-$HOME_DIR/.nvm/versions/node/v22.19.0/bin/cloudflared}"
CF_TUNNEL_NAME="${CF_TUNNEL_NAME:-stelae}"
CF_DIR="$HOME_DIR/.cloudflared"
CF_CONF="$CF_DIR/config.yml"

# public URL for probes
if [ -z "${PUBLIC_BASE_URL:-}" ] && [ -f "$STELAE_ENV_FILE" ]; then
  PUBLIC_BASE_URL="$(grep -E '^PUBLIC_BASE_URL=' "$STELAE_ENV_FILE" 2>/dev/null | sed 's/^[^=]*=//')"
fi
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://mcp.infotopology.xyz}"

# readiness thresholds
MIN_TOOL_COUNT="${MIN_TOOL_COUNT:-2}"             # “warm enough” before exposing
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-45}"
CURL_MAX_TIME="${CURL_MAX_TIME:-45}"

# options ----------------------------------------------------------------------
START_CLOUDFLARED=1
START_BRIDGE=1
START_WATCHDOG=1
KEEP_PM2=0
FULL_REDEPLOY=0
RUN_POPULATE=1
for arg in "$@"; do
  case "$arg" in
    --no-cloudflared) START_CLOUDFLARED=0;;
    --no-bridge) START_BRIDGE=0;;
    --no-watchdog) START_WATCHDOG=0;;
    --keep-pm2) KEEP_PM2=1;;
    --full) FULL_REDEPLOY=1;;
    --skip-populate-overrides) RUN_POPULATE=0;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [options]
  --no-cloudflared          Skip starting cloudflared via pm2
  --no-bridge               Skip starting the streamable bridge
  --no-watchdog             Skip starting the public tunnel watchdog
  --keep-pm2                Do not 'pm2 kill'; just (re)start managed apps
  --full                    Also push manifest to Cloudflare KV and deploy worker
  --skip-populate-overrides Do not auto-refresh config/tool_overrides.json

Env overrides:
  PROXY_PORT        (default 9090)
  MIN_TOOL_COUNT    (default 2)
  READY_TIMEOUT_SEC (default 45)
EOF
      exit 0
    ;;
  esac
done

# helpers ----------------------------------------------------------------------

ensure_pm2_app() {
  local app="$1"
  local status
  status=$(pm2 jlist | jq -r --arg name "$app" '.[] | select(.name==$name) | .pm2_env.status' 2>/dev/null || true)
  if [ -z "$status" ] || [ "$status" = "null" ]; then
    log "pm2 ensure ${app}: status=absent -> start"
    pm2 start "$ECOSYSTEM" --only "$app"
    return
  fi
  if [ "$status" != "online" ]; then
    log "pm2 ensure ${app}: status=${status} -> delete+start"
    pm2 delete "$app" >/dev/null 2>&1 || true
    pm2 start "$ECOSYSTEM" --only "$app"
    return
  fi
  log "pm2 ensure ${app}: status=online -> restart"
  pm2 restart "$app" --update-env
}

wait_port() {
  local port="$1" label="$2" tries=60 interval=0.25 attempt timeout
  timeout=$(awk -v t="$tries" -v i="$interval" 'BEGIN{printf "%.1f", t*i}')
  log "Waiting for $label to listen on :$port (timeout ~${timeout}s)…"
  for attempt in $(seq 1 $tries); do
    if ss -ltn "( sport = :$port )" | grep -q ":$port"; then
      log "$label is listening on :$port (attempt ${attempt}/${tries})"
      return 0
    fi
    if (( attempt % 10 == 0 )); then
      log "Still waiting for $label on :$port (attempt ${attempt}/${tries})"
    fi
    sleep "$interval"
  done
  err "$label did not bind :$port after ${timeout}s."
  return 1
}

probe_jsonrpc_initialize() {
  local url="http://127.0.0.1:${PROXY_PORT}/mcp"
  local payload='{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2024-11-05"}}'
  local waits=(0 0.5 1 2 4)
  local attempt=0
  local last_status=""
  local last_body=""
  log "Local probe: initialize (JSON-RPC with backoff)"
  for delay in "${waits[@]}"; do
    if (( attempt > 0 )); then
      sleep "$delay"
    fi
    attempt=$((attempt + 1))
    local hdr_file body_file status
    hdr_file=$(mktemp)
    body_file=$(mktemp)
    if curl --max-time "$CURL_MAX_TIME" -sS -D "$hdr_file" -o "$body_file" \
        -H 'Content-Type: application/json' --data "$payload" "$url"; then
      if jq -e '.result' "$body_file" >/dev/null 2>&1; then
        local summary
        summary=$(jq -c '{server: (.result.serverInfo?.name // "unknown"), capabilities: (.result.capabilities? | keys)}' "$body_file" 2>/dev/null || true)
        log "JSON-RPC initialize succeeded on attempt ${attempt}: ${summary:-ok}"
        jq -C '.' "$body_file" || cat "$body_file"
        rm -f "$hdr_file" "$body_file"
        return 0
      fi
    fi
    status=$(sed -n '1p' "$hdr_file" 2>/dev/null || true)
    last_status="${status:-curl failed}"
    last_body=$(head -c 400 "$body_file" 2>/dev/null | tr -d '\r')
    rm -f "$hdr_file" "$body_file"
  done
  err "JSON-RPC probe failed for ${url} after ${attempt} attempt(s) (last status: ${last_status:-<none>})"
  if [ -n "$last_body" ]; then
    echo "--- last response body (truncated) ---"
    printf '%s\n' "$last_body"
  fi
  return 1
}

local_tool_count() {
  local payload count
  payload=$(curl --max-time "$CURL_MAX_TIME" -s "http://127.0.0.1:${PROXY_PORT}/mcp" \
    -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' 2>/dev/null || true)
  if [ -z "$payload" ]; then
    echo 0
    return
  fi
  count=$(printf '%s' "$payload" | jq -r 'try (.result.tools|length) catch ""' 2>/dev/null || true)
  if [[ "$count" =~ ^[0-9]+$ ]]; then
    echo "$count"
  else
    echo 0
  fi
}

wait_tools_ready() {
  log "Waiting for tools to register (target >= ${MIN_TOOL_COUNT}, timeout ${READY_TIMEOUT_SEC}s)…"
  local start ts count=0 last_log
  start=$(date +%s)
  last_log=$start
  while :; do
    count="$(local_tool_count)"
    if [ "${count:-0}" -ge "$MIN_TOOL_COUNT" ]; then
      log "Tool catalog ready: ${count} tools."
      return 0
    fi
    ts=$(date +%s)
    if [ $((ts - last_log)) -ge 5 ]; then
      log "Still waiting for tools (current count=${count:-0})"
      last_log=$ts
    fi
    if [ $((ts - start)) -ge "$READY_TIMEOUT_SEC" ]; then
      warn "Timed out at ${count} tools; continuing (public may briefly see fewer tools)."
      return 0
    fi
    sleep 1
  done
}

populate_overrides_via_proxy() {
  if [ "$RUN_POPULATE" -ne 1 ]; then
    warn "Skipping tool override population (--skip-populate-overrides)."
    return
  fi
  local url="$1" start elapsed
  start=$(date +%s)
  if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    warn "Skipping tool override population; PYTHON=$PYTHON_BIN not executable"
    return
  fi
  local output
  if output=$(PYTHONPATH="$STELAE_DIR" "$PYTHON_BIN" "$STELAE_DIR/scripts/populate_tool_overrides.py" --proxy-url "$url" --quiet 2>&1); then
    local summary
    summary=$(echo "$output" | grep -E "^(No schema updates required|Wrote updated overrides)" | tail -1)
    if [ -z "$summary" ]; then
      summary="No schema updates required"
    fi
    elapsed=$(( $(date +%s) - start ))
    log "Tool overrides synced via proxy catalog (${summary}; ${elapsed}s)"
  else
    elapsed=$(( $(date +%s) - start ))
    warn "Tool override population failed via proxy (${elapsed}s)"
    printf '%s\n' "$output"
  fi
}

prepare_tool_aggregations() {
  local script="$STELAE_DIR/scripts/process_tool_aggregations.py"
  if [ ! -f "$script" ]; then
    return
  fi
  local python_exec="$PYTHON_BIN"
  if [ -z "$python_exec" ] || [ ! -x "$python_exec" ]; then
    python_exec="$(command -v python3 || true)"
    if [ -z "$python_exec" ]; then
      warn "Skipping tool aggregation prep; python3 not available"
      return
    fi
  fi
  local output
  if output=$(PYTHONPATH="$STELAE_DIR" "$python_exec" "$script" --scope local 2>&1); then
    local summary
    summary=$(echo "$output" | tail -1)
    log "Tool aggregations prepared (${summary:-ok})"
  else
    warn "Tool aggregation prep failed"
    printf '%s\n' "$output"
  fi
}

ensure_cloudflared_ingress() {
  mkdir -p "$CF_DIR"
  local tuuid
  tuuid="$("$CLOUDFLARED_BIN" tunnel list 2>/dev/null | awk -v n="$CF_TUNNEL_NAME" '$2==n{print $1}' | head -n1 || true)"
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
  "$CLOUDFLARED_BIN" tunnel ingress validate || warn "cloudflared ingress validate returned non-zero"
  "$CLOUDFLARED_BIN" tunnel route dns "$CF_TUNNEL_NAME" mcp.infotopology.xyz >/dev/null 2>&1 || true
}

show_public_jsonrpc_once() {
  local url="$1"
  local hdrs body status ctype cfray rc=1
  hdrs="$(mktemp)"
  body="$(curl --max-time "$CURL_MAX_TIME" -sk -D "$hdrs" \
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
require go
if [ -s "$HOME_DIR/.nvm/nvm.sh" ]; then . "$HOME_DIR/.nvm/nvm.sh"; fi
require pm2
if [ "$FULL_REDEPLOY" -eq 1 ]; then
  require npx
fi
mkdir -p "$STELAE_DIR/logs"

log "Validating tool aggregation config"
prepare_tool_aggregations

# build fresh proxy binary before restarting services
log "Building mcp-proxy binary → $PROXY_BIN"
build_start=$(date +%s)
(
  cd "$PROXY_DIR"
  mkdir -p "$(dirname "$PROXY_BIN")"
  go build -o "$PROXY_BIN" ./...
)
log "mcp-proxy build completed in $(( $(date +%s) - build_start ))s"

# stop / clean -----------------------------------------------------------------
if [ "$KEEP_PM2" -eq 0 ]; then
  log "Killing pm2 (all processes)…"
  pm2 kill || true
  rm -f "$HOME_DIR/.pm2/pm2.pid" || true
  log "pm2 kill completed"
else
  warn "--keep-pm2 set: will not kill pm2, only restart known apps"
fi

log "Killing stray listeners on :$PROXY_PORT (if any)…"
mapfile -t PIDS < <(ss -ltnp "( sport = :$PROXY_PORT )" | awk -F',' '/pid=/{print $2}' | sed 's/pid=//' | awk '{print $1}' | sort -u)
if [ "${#PIDS[@]}" -gt 0 ]; then
  for pid in "${PIDS[@]}"; do kill -9 "$pid" 2>/dev/null || true; done
  log "Killed ${#PIDS[@]} listener(s) on :$PROXY_PORT"
else
  log "No stray listeners detected on :$PROXY_PORT"
fi

# render proxy config ----------------------------------------------------------
log "Rendering proxy config → $PROXY_JSON"
python3 "$RENDERER" --template "$PROXY_TEMPLATE" --output "$PROXY_JSON" --env-file "$STELAE_ENV_FILE" --fallback-env "$STELAE_DIR/.env.example"
python3 - <<'PY' "$PROXY_JSON"
import json,sys; json.load(open(sys.argv[1]))
PY

# start local proxy + servers --------------------------------------------------
log "Starting mcp-proxy via pm2"
ensure_pm2_app mcp-proxy

if [ "$START_BRIDGE" -eq 1 ]; then
  log "Starting stelae-bridge via pm2"
  ensure_pm2_app stelae-bridge
else
  warn "Skipping stelae-bridge (--no-bridge)."
fi

if [ "$START_WATCHDOG" -eq 1 ]; then
  log "Starting watchdog via pm2"
  ensure_pm2_app watchdog
else
  warn "Skipping watchdog (--no-watchdog)."
fi

pm2 save || true
log "pm2 process list saved (core services)"

wait_port "$PROXY_PORT" "mcp-proxy" || { err "proxy didn’t bind :$PROXY_PORT"; pm2 logs mcp-proxy --lines 120; exit 2; }

# local readiness (before exposing) -------------------------------------------
log "Local probe: HEAD http://127.0.0.1:${PROXY_PORT}/mcp"
curl --max-time "$CURL_MAX_TIME" -sI "http://127.0.0.1:${PROXY_PORT}/mcp" | sed -n '1,10p' || true

probe_jsonrpc_initialize

wait_tools_ready

log "Syncing tool overrides via proxy catalog"
populate_overrides_via_proxy "http://127.0.0.1:${PROXY_PORT}/mcp"

log "Capturing live catalog snapshot"
if STELAE_STATE_HOME="$STELAE_STATE_HOME" \
   STELAE_PROXY_BASE="http://127.0.0.1:${PROXY_PORT}" \
   python3 "$STELAE_DIR/scripts/capture_live_catalog.py"; then
  :
else
  warn "Live catalog capture failed (continuing)."
fi

if command -v python3 >/dev/null 2>&1; then
  catalog_diff_out=$(python3 "$STELAE_DIR/scripts/diff_catalog_snapshots.py" --fail-on-drift 2>/dev/null || true)
  if [ -n "$catalog_diff_out" ]; then
    log "Catalog diff (intended vs live):"
    printf '%s\n' "$catalog_diff_out"
  fi
  catalog_metrics_out=$(python3 "$STELAE_DIR/scripts/catalog_metrics.py" 2>/dev/null || true)
  if [ -n "$catalog_metrics_out" ]; then
    log "Catalog metrics:"
    printf '%s\n' "$catalog_metrics_out"
  fi
  prune_out=$(python3 "$STELAE_DIR/scripts/prune_catalog_history.py" 2>/dev/null || true)
  if [ -n "$prune_out" ]; then
    log "Catalog history prune: $prune_out"
  fi
fi

log "Local probe: tools/list → names (first 40)"
curl --max-time "$CURL_MAX_TIME" -s "http://127.0.0.1:${PROXY_PORT}/mcp" -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,40p' || true

if [ "$FULL_REDEPLOY" -eq 1 ]; then
  log "Full redeploy: pushing manifest to Cloudflare KV"
  (
    cd "$STELAE_DIR"
    PORT="$PROXY_PORT" bash scripts/push_manifest_to_kv.sh
  ) || warn "push_manifest_to_kv.sh failed; continuing"
fi

# start cloudflared only when local is warm -----------------------------------
if [ "$START_CLOUDFLARED" -eq 1 ]; then
  require "$CLOUDFLARED_BIN"
  command -v cloudflared >/dev/null 2>&1 || PATH="$PATH:$(dirname "$CLOUDFLARED_BIN")"
  ensure_cloudflared_ingress
  log "Starting cloudflared via pm2"
  ensure_pm2_app cloudflared
  pm2 save || true
  log "pm2 process list saved (cloudflared)"
else
  warn "Skipping cloudflared (--no-cloudflared)."
fi

# public probes (best-effort; tolerate CF 530 blips) ---------------------------
if [ "$START_CLOUDFLARED" -eq 1 ] && [ -n "$PUBLIC_BASE_URL" ]; then
  log "Public probe: manifest"
  curl --max-time "$CURL_MAX_TIME" -skI "${PUBLIC_BASE_URL}/.well-known/mcp/manifest.json" | sed -n '1,12p' || true

  log "Public probe: tools/list (JSON-RPC, retry + diagnostics)"
  show_public_jsonrpc_retry "${PUBLIC_BASE_URL}/mcp" || true
fi

log "Done. For issues, check: 'pm2 logs mcp-proxy --lines 150' and 'pm2 logs cloudflared --lines 80'."
