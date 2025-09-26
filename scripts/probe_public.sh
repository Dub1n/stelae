#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-https://mcp.infotopology.xyz}"
echo "==> Public probe: HEAD $BASE/mcp"
curl -sI "$BASE/mcp" | sed -n '1,12p' || true
echo "==> Public probe: POST initialize"
curl -skX POST "$BASE/mcp" \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05"}}' -i | sed -n '1,12p' || true
echo "==> Public probe: GET $BASE/healthz"
curl -sk "$BASE/healthz" | jq . || cat
echo "==> Public probe: GET $BASE/version"
curl -sk "$BASE/version" | jq . || cat
echo "==> Public probe: manifest passthrough"
curl -sk "$BASE/.well-known/mcp/manifest.json" | jq '{tools: (.tools|map(.name))}' || cat
