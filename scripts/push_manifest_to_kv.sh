# stelae/scripts/push_manifest_to_kv.sh
#!/usr/bin/env bash
set -euo pipefail

# ---- config ----
PORT="${PUBLIC_PORT:-9090}"
SRC="http://127.0.0.1:${PORT}/.well-known/mcp/manifest.json"

WORKER_DIR="${WORKER_DIR:-$HOME/dev/stelae/cloudflare/worker}"

# KV namespace friendly name (as shown by `wrangler kv namespace list`)
NAMESPACE_NAME="${NAMESPACE_NAME:-stelae-manifest}"

# The key under which we store the JSON
KEY="${KEY:-manifest_json}"

# ---- preflight ----
command -v wrangler >/dev/null || { echo "wrangler not found in PATH" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found in PATH" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl not found in PATH" >&2; exit 1; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "==> fetching origin manifest: $SRC"
curl -fsSL "$SRC" -o "$tmp"

# sanity: must be JSON with endpoint/endpointURL
if ! jq -e '.endpoint // .endpointURL' "$tmp" >/dev/null 2>&1; then
  echo "error: fetched manifest missing endpoint/endpointURL fields" >&2
  exit 2
fi

# ---- resolve namespace id from title ----
echo "==> resolving KV namespace id for title: ${NAMESPACE_NAME}"
NS_JSON="$(wrangler kv namespace list 2>/dev/null || true)"
if [ -z "$NS_JSON" ]; then
  echo "error: could not list KV namespaces (wrangler auth/config?)" >&2
  exit 3
fi

NAMESPACE_ID="$(echo "$NS_JSON" | jq -r --arg t "$NAMESPACE_NAME" '
  .[] | select(.title==$t) | .id
' | head -n1)"

if [ -z "${NAMESPACE_ID:-}" ] || [ "$NAMESPACE_ID" = "null" ]; then
  echo "error: namespace \"$NAMESPACE_NAME\" not found. Run: wrangler kv namespace create $NAMESPACE_NAME" >&2
  exit 4
fi
echo "    -> namespace id: $NAMESPACE_ID"

# ---- deploy worker (idempotent) ----
if [ -d "$WORKER_DIR" ]; then
  echo "==> deploying worker from: $WORKER_DIR"
  ( cd "$WORKER_DIR" && wrangler deploy )
else
  echo "warn: WORKER_DIR not found ($WORKER_DIR); skipping deploy" >&2
fi

# ---- write KV using --namespace-id ----
echo "==> pushing manifest to KV (namespace-id=$NAMESPACE_ID, key=$KEY)…"
wrangler kv key put --namespace-id "$NAMESPACE_ID" "$KEY" --path "$tmp"

echo "ok: KV updated."
