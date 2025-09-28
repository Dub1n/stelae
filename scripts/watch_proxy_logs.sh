  #!/usr/bin/env bash
  set -euo pipefail
  tail -F "$HOME/dev/stelae/logs/mcp-proxy.err.log" "$HOME/dev/stelae/logs/mcp-proxy.out.log"
