#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TARGET="$SCRIPT_DIR/restart_stelae.sh"

if [ ! -x "$TARGET" ]; then
  chmod +x "$TARGET"
fi

exec "$TARGET" "$@"
