#!/usr/bin/env bash
set -euo pipefail

# scripts/shadow_diff_smoke.sh
#
# PR-E.1: Smoke test for shadow diff feature (Paper vs Live).
#
# This script validates that:
# 1. shadow_diff.py runs correctly with paper and live fixtures
# 2. The output JSON contains diff_metrics.v1 schema
# 3. Expected values are present:
#    - rows_matched: 2
#    - fill_match_rate: 0.5 (one matched, one not)
#    - slippage_diff_bps: > 0 (for the filled signal)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT="/tmp/shadow_diff_output.json"

# Clean up any previous run
rm -f "$OUT"

# Run shadow_diff.py with fixtures
echo "[shadow_diff_smoke] Running shadow_diff.py with paper/live fixtures..." >&2

python3 -m integration.shadow_diff \
    --paper "integration/fixtures/shadow_diff/paper.jsonl" \
    --live "integration/fixtures/shadow_diff/live.jsonl" \
    --out "$OUT" 2>&1 | grep -v "^OK" >&2

# Validate output file exists
if [[ ! -f "$OUT" ]]; then
    echo "[shadow_diff_smoke] FAIL: Output file does not exist: $OUT" >&2
    exit 1
fi
echo "[shadow_diff_smoke] Assertion 1 passed: Output file exists" >&2

# Validate output is valid JSON and contains expected structure/values
python3 <<'PYTHON' 2>&1
import json
import sys

out_file = "/tmp/shadow_diff_output.json"

try:
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    print(f"[shadow_diff_smoke] FAIL: Output is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

# Check schema_version
if data.get("schema_version") != "diff_metrics.v1":
    print(f"[shadow_diff_smoke] FAIL: schema_version != 'diff_metrics.v1', got: {data.get('schema_version')}", file=sys.stderr)
    sys.exit(1)
print("[shadow_diff_smoke] Assertion 2 passed: schema_version == 'diff_metrics.v1'", file=sys.stderr)

# Check rows_matched == 2
rows_matched = data.get("summary", {}).get("rows_matched")
if rows_matched != 2:
    print(f"[shadow_diff_smoke] FAIL: rows_matched != 2, got: {rows_matched}", file=sys.stderr)
    sys.exit(1)
print("[shadow_diff_smoke] Assertion 3 passed: rows_matched == 2", file=sys.stderr)

# Check fill_match_rate == 0.5
fill_match_rate = data.get("summary", {}).get("fill_match_rate")
if fill_match_rate != 0.5:
    print(f"[shadow_diff_smoke] FAIL: fill_match_rate != 0.5, got: {fill_match_rate}", file=sys.stderr)
    sys.exit(1)
print("[shadow_diff_smoke] Assertion 4 passed: fill_match_rate == 0.5", file=sys.stderr)

# Check slippage_diff_bps > 0 for matched filled trades
# Sig1: paper_price=100.0, live_price=101.0 -> slippage = ((101-100)/100)*10000 = 100 bps
slippage_bps_values = [row.get("slippage_bps", 0) for row in data.get("rows", [])]
if not any(s > 0 for s in slippage_bps_values):
    print(f"[shadow_diff_smoke] FAIL: No positive slippage_bps found, got: {slippage_bps_values}", file=sys.stderr)
    sys.exit(1)
print(f"[shadow_diff_smoke] Assertion 5 passed: slippage_bps > 0 found: {slippage_bps_values}", file=sys.stderr)

# Check rows array contains expected signal_ids
signal_ids = [row.get("signal_id") for row in data.get("rows", [])]
if sorted(signal_ids) != ["Sig1", "Sig2"]:
    print(f"[shadow_diff_smoke] FAIL: Expected signal_ids ['Sig1', 'Sig2'], got: {signal_ids}", file=sys.stderr)
    sys.exit(1)
print("[shadow_diff_smoke] Assertion 6 passed: rows contain expected signal_ids", file=sys.stderr)

print("[shadow_diff_smoke] OK ✅", file=sys.stderr)
PYTHON

echo "[shadow_diff_smoke] All assertions passed" >&2
