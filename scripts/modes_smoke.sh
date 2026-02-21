#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CFG="integration/fixtures/config/modes_two_profiles.yaml"

TRADES_XY="integration/fixtures/trades.modes_two_profiles.jsonl"
EXPECTED_XY="integration/fixtures/expected_modes_two_profiles.json"

TRADES_UNKNOWN="integration/fixtures/trades.modes_unknown.jsonl"
EXPECTED_UNKNOWN="integration/fixtures/expected_modes_unknown.json"

TRADES_NOMODE="integration/fixtures/trades.modes_nomode.jsonl"
EXPECTED_NOMODE="integration/fixtures/expected_modes_nomode.json"

tmp_stdout="$(mktemp)"
tmp_stderr="$(mktemp)"
trap 'rm -f "$tmp_stdout" "$tmp_stderr"' EXIT

run_case() {
  local trades_path="$1"
  local expected_path="$2"

  : >"$tmp_stdout"
  : >"$tmp_stderr"

  set +e
  python3 -m integration.paper_pipeline \
    --dry-run \
    --config "$CFG" \
    --trades-jsonl "$trades_path" \
    --summary-json \
    --token-snapshot integration/fixtures/token_snapshot.sample.csv \
    --wallet-profiles integration/fixtures/wallet_profiles.sample.csv \
    --allowlist strategy/wallet_allowlist.yaml \
    1>"$tmp_stdout" 2>"$tmp_stderr"
  rc=$?
  set -e

  if [[ $rc -ne 0 ]]; then
    echo "ERROR: modes_smoke: paper_pipeline failed rc=$rc" >&2
    cat "$tmp_stderr" >&2 || true
    exit 1
  fi

  # stdout must be exactly 1 non-empty line
  non_empty_lines=$(grep -cve '^\s*$' "$tmp_stdout" || true)
  if [[ "$non_empty_lines" -ne 1 ]]; then
    echo "ERROR: modes_smoke: expected stdout=1 line, got $non_empty_lines" >&2
    echo "--- stdout ---" >&2
    cat "$tmp_stdout" >&2 || true
    echo "--- stderr ---" >&2
    cat "$tmp_stderr" >&2 || true
    exit 1
  fi

  python3 - "$tmp_stdout" "$expected_path" <<'PY'
import json, sys
from pathlib import Path

stdout_path = Path(sys.argv[1])
expected_path = Path(sys.argv[2])

try:
    line = stdout_path.read_text(encoding="utf-8").strip().splitlines()[-1]
except Exception:
    sys.stderr.write("ERROR: modes_smoke: expected stdout=1 line, got 0\n")
    raise SystemExit(1)

try:
    summary = json.loads(line)
except Exception:
    sys.stderr.write("ERROR: modes_smoke: invalid JSON on stdout\n")
    raise SystemExit(1)

def require(obj, key):
    if key not in obj:
        sys.stderr.write(f"ERROR: modes_smoke: summary missing key: {key}\n")
        raise SystemExit(1)
    return obj[key]

counts = require(summary, "counts")
mode_counts = require(summary, "mode_counts")

expected = json.loads(expected_path.read_text(encoding="utf-8"))
exp_modes = expected.get("expected_mode_names", [])
exp_total = expected.get("expected_total_lines")
exp_totals = expected.get("expected_mode_totals", {})

for m in exp_modes:
    if m not in mode_counts:
        sys.stderr.write(f"ERROR: modes_smoke: mode_counts missing mode: {m}\n")
        raise SystemExit(1)
    got = mode_counts[m].get("total_lines")
    if got != exp_totals.get(m):
        sys.stderr.write(f"ERROR: modes_smoke: mode {m} total_lines expected=1 got={got}\n")
        raise SystemExit(1)

sum_total = sum(int(v.get("total_lines", 0)) for v in mode_counts.values())
counts_total = counts.get("total_lines")

if counts_total != exp_total or sum_total != exp_total:
    sys.stderr.write(
        f"ERROR: modes_smoke: total_lines mismatch: counts.total_lines={counts_total} sum(mode_counts.total_lines)={sum_total}\n"
    )
    raise SystemExit(1)
PY
}

# Case 1: explicit X/Y modes
run_case "$TRADES_XY" "$EXPECTED_XY"

# Case 2: explicit unknown mode -> __unknown_mode__
run_case "$TRADES_UNKNOWN" "$EXPECTED_UNKNOWN"

# Case 3: missing mode -> fallback (X for current registry)
run_case "$TRADES_NOMODE" "$EXPECTED_NOMODE"

echo "[modes_smoke] OK ✅" >&2
