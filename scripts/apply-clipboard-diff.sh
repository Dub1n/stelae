#!/usr/bin/env bash
# apply-clipboard-diff.sh (awk-free)
# Read diff from clipboard or a file arg, normalize, validate, try git apply, fallback to patch with -p autodetect.

set -euo pipefail

err(){ printf "error: %s\n" "$*" >&2; exit 1; }
note(){ printf "• %s\n" "$*" >&2; }

need(){ command -v "$1" >/dev/null 2>&1 || err "missing dependency: $1"; }
need patch

have_git=0
command -v git >/dev/null 2>&1 && have_git=1

# if we're in a git repo, operate at repo root regardless of where the script lives
if [ "${1-}" != "--no-git-root" ] && [ $have_git -eq 1 ] && git rev-parse --show-toplevel >/dev/null 2>&1; then
  cd "$(git rev-parse --show-toplevel)" || err "failed to cd to repo root"
fi

tmp="$(mktemp -t clipdiff.XXXXXX)" || err "mktemp failed"
trap 'rm -f "$tmp"' EXIT

# -------- get input --------
get_clipboard() {
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command Get-Clipboard -Raw 2>/dev/null
  elif command -v wl-paste >/dev/null 2>&1; then
    wl-paste
  elif command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard -o
  elif command -v xsel >/dev/null 2>&1; then
    xsel -b -o
  elif command -v pbpaste >/dev/null 2>&1; then
    pbpaste
  else
    err "no clipboard tool found (powershell.exe / wl-paste / xclip / xsel / pbpaste)"
  fi
}

# allow a file arg as well: ./apply-clipboard-diff.sh patch.diff
if [ "${1-}" ] && [ -f "${1-}" ] && [ "$1" != "--no-git-root" ]; then
  cp "$1" "$tmp"
else
  get_clipboard > "$tmp" || err "couldn’t read clipboard"
fi

# -------- normalize --------
if command -v dos2unix >/dev/null 2>&1; then
  dos2unix -q "$tmp" 2>/dev/null || true
else
  sed -i 's/\r$//' "$tmp"
fi

# unindent accidentally spaced control lines
sed -i -E 's/^[[:space:]]+(---|\+\+\+|@@) /\1 /' "$tmp"

# -------- sanity checks (light) --------
grep -qE '^(---|\+\+\+) ' "$tmp" || err "missing file headers (---/+++). ask agent for unified diff with headers."
grep -qE '^@@ -[0-9]+(,[0-9]+)? \+[0-9]+(,[0-9]+)? @@' "$tmp" || err "no valid hunk headers (need @@ -start,len +start,len @@)."

# -------- try git apply first --------
if [ $have_git -eq 1 ]; then
  note "checking with git apply --check ..."
  if git apply --check "$tmp" >/dev/null 2>&1; then
    note "applying with git apply ..."
    git apply "$tmp"
    echo "[x] applied via git"
    exit 0
  else
    note "git apply --check failed; falling back to patch(1)."
  fi
fi

# -------- fallback: patch(1) with -p autodetect --------
if grep -qE '^--- a/|^\+\+\+ b/' "$tmp"; then
  order=(1 0 2 3 4 5 6 7 8 9 10)
else
  order=(0 1 2 3 4 5 6 7 8 9 10)
fi

chosen=""
for N in "${order[@]}"; do
  if patch --dry-run -p"$N" -l -F3 < "$tmp" >/dev/null 2>&1; then
    chosen="$N"; break
  fi
done

[ -n "$chosen" ] || {
  note "couldn’t find a working strip level. headers:"
  grep -E '^(---|\+\+\+) ' "$tmp" | sed 's/^/  /' >&2
  err "no match — ensure you’re at the correct repo root and paths exist."
}

note "applying with patch -p$chosen ..."
patch -p"$chosen" -l -F3 < "$tmp"
echo "[x] applied via patch (-p$chosen)"
