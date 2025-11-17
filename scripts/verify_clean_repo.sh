#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/verify_clean_repo.sh [options]

Run the default render + restart automation and assert that tracked files remain unchanged.

Options:
  --skip-render     Skip the make render-proxy step (not recommended).
  --skip-restart    Skip scripts/run_restart_stelae.sh (useful when pm2/cloudflared aren't installed).
  -h, --help        Show this help message.

Environment:
  VERIFY_CLEAN_RESTART_ARGS  Override the restart arguments (default:
                             "--keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides").
EOF
}

SKIP_RENDER=0
SKIP_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-render)
      SKIP_RENDER=1
      shift
      ;;
    --skip-restart)
      SKIP_RESTART=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "verify-clean: unknown option '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)

if [[ -n "${VERIFY_CLEAN_RESTART_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  RESTART_ARGS=(${VERIFY_CLEAN_RESTART_ARGS})
else
  RESTART_ARGS=(--keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides)
fi

before_status=$(mktemp)
after_status=$(mktemp)
trap 'rm -f "$before_status" "$after_status"' EXIT

git -C "$REPO_ROOT" status --porcelain > "$before_status"
if [[ -s "$before_status" ]]; then
  echo "verify-clean: working tree already has local changes; comparing relative to current snapshot." >&2
fi

run_step() {
  local label=$1
  shift
  echo "==> $label"
  (cd "$REPO_ROOT" && "$@")
}

if [[ $SKIP_RENDER -eq 0 ]]; then
  run_step "make render-proxy" make render-proxy
else
  echo "==> Skipping render-proxy step"
fi

if [[ $SKIP_RESTART -eq 0 ]]; then
  run_step "restart stack" "$REPO_ROOT/scripts/run_restart_stelae.sh" "${RESTART_ARGS[@]}"
else
  echo "==> Skipping restart step"
fi

if [[ "${STELAE_ALLOW_LIVE_DRIFT:-0}" =~ ^(1|true|yes|on)$ ]]; then
  echo "==> Skipping catalog drift enforcement (STELAE_ALLOW_LIVE_DRIFT set)"
else
  if command -v python3 >/dev/null 2>&1; then
    echo "==> Checking catalog drift (intended vs live)"
    if ! (cd "$REPO_ROOT" && python3 scripts/diff_catalog_snapshots.py --fail-on-drift); then
      echo "verify-clean: catalog drift detected. Set STELAE_ALLOW_LIVE_DRIFT=1 to bypass." >&2
      exit 1
    fi
  else
    echo "==> python3 not available; skipping catalog drift check"
  fi
fi

git -C "$REPO_ROOT" status --porcelain > "$after_status"
if ! cmp -s "$before_status" "$after_status"; then
  echo "verify-clean: tracked files changed after automation." >&2
  git -C "$REPO_ROOT" status --short >&2
  exit 1
fi

echo "verify-clean: working tree clean after automation."
