#!/usr/bin/env bash
set -euo pipefail

# Build a clean zip that contains ONLY git-tracked files.
# This prevents accidental inclusion of __pycache__ / *.pyc and other local artifacts.

OUT="${1:-repo.zip}"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

tmp_list="$(mktemp)"
trap 'rm -f "$tmp_list"' EXIT

git ls-files > "$tmp_list"

rm -f "$OUT"
zip -q -@ "$OUT" < "$tmp_list"
echo "OK: wrote $OUT" >&2
