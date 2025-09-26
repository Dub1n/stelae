# scripts/clean_and_apply_diff.sh
#!/usr/bin/env bash
set -euo pipefail
f="${1:-/dev/stdin}"
tmp="$(mktemp)"
# 1) normalize line endings + strip BOM/ZWSP/NBSP + remove fences/indent
sed 's/\r$//' "$f" \
| perl -CS -pe 's/\x{FEFF}//g; s/\x{200B}//g; s/\x{200C}//g; s/\x{200D}//g; s/\x{00A0}/ /g' \
| awk '
  BEGIN{inblock=0}
  # kill ``` fences and leading spaces before ---/+++
  /^```/ { next }
  /^[[:space:]]+--- a\// { sub(/^[[:space:]]+/,""); print; next }
  /^[[:space:]]+\+\+\+ b\// { sub(/^[[:space:]]+/,""); print; next }
  { print }
' > "$tmp"

# 2) sanity check: headers + hunks present
head -n3 "$tmp" | grep -qx '--- a/.*' && true
sed -n '2p' "$tmp" | grep -qx '+++ b/.*' && true
grep -q '^@@ ' "$tmp"

# 3) dry-run then apply with -p1 from repo root
git rev-parse --show-toplevel >/dev/null
git apply --check -p1 "$tmp"
git apply -p1 --index "$tmp"
echo "applied OK"
