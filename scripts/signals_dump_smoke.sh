#!/usr/bin/env bash
set -euo pipefail

# scripts/signals_dump_smoke.sh
#
# PR-8.1: Smoke test for signals dump feature.
#
# This script validates that:
# 1. The paper pipeline correctly writes signals JSONL output
# 2. The output file contains the expected schema and fields
# 3. Simulation results are correctly included when --signals-include-sim is used

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT="/tmp/signals_dump.jsonl"

# Clean up any previous run
rm -f "$OUT"

# Run the paper pipeline with signals dump enabled
echo "[signals_dump_smoke] Running paper_pipeline with signals dump..." >&2

# Assertions:
# 1) stdout has exactly 1 line (from --summary-json)
STDOUT_OUTPUT=$(python3 -m integration.paper_pipeline --dry-run --summary-json --sim-preflight \
  --signals-out "$OUT" --signals-include-sim \
  --config integration/fixtures/config/sim_preflight.yaml \
  --allowlist strategy/wallet_allowlist.yaml \
  --token-snapshot integration/fixtures/token_snapshot.sim_preflight.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.sim_preflight.csv \
  --trades-jsonl integration/fixtures/trades.sim_preflight.jsonl 2>/dev/null)

LINE_COUNT=$(echo "$STDOUT_OUTPUT" | grep -c . || echo "0")
if [[ "$LINE_COUNT" -ne 1 ]]; then
  echo "ERROR: Expected 1 line on stdout, got $LINE_COUNT" >&2
  exit 1
fi
echo "[signals_dump_smoke] Assertion 1 passed: stdout has exactly 1 line" >&2

# 2) $OUT exists and is non-empty
if [[ ! -f "$OUT" ]]; then
  echo "ERROR: signals-out file does not exist: $OUT" >&2
  exit 1
fi
if [[ ! -s "$OUT" ]]; then
  echo "ERROR: signals-out file is empty: $OUT" >&2
  exit 1
fi
echo "[signals_dump_smoke] Assertion 2 passed: $OUT exists and is non-empty" >&2

# 3) line count == 2 (ENTER for both trades in sim_preflight fixture)
JQ_COUNT=$(wc -l < "$OUT")
if [[ "$JQ_COUNT" -ne 2 ]]; then
  echo "ERROR: Expected 2 lines in signals dump, got $JQ_COUNT" >&2
  exit 1
fi
echo "[signals_dump_smoke] Assertion 3 passed: line count == 2" >&2

# 4) Each line parses as JSON with required fields
python3 <<'PYTHON'
import json
import sys

out_file = "/tmp/signals_dump.jsonl"
with open(out_file, "r", encoding="utf-8") as f:
    lines = [l.strip() for l in f.readlines() if l.strip()]

if len(lines) != 2:
    print("ERROR: Expected 2 lines", file=sys.stderr)
    sys.exit(1)

linenos = set()
for i, line in enumerate(lines, start=1):
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        print(f"ERROR: Line {i} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check required fields
    if obj.get("schema_version") != "signals.v1":
        print(f"ERROR: Line {i}: schema_version != 'signals.v1'", file=sys.stderr)
        sys.exit(1)
    
    if obj.get("decision") != "ENTER":
        print(f"ERROR: Line {i}: decision != 'ENTER'", file=sys.stderr)
        sys.exit(1)
    
    if obj.get("reject_reason") is not None:
        print(f"ERROR: Line {i}: reject_reason should be null", file=sys.stderr)
        sys.exit(1)
    
    if obj.get("sim_exit_reason") not in {"TP", "SL", "TIME"}:
        print(f"ERROR: Line {i}: sim_exit_reason not in {{TP, SL, TIME}}", file=sys.stderr)
        sys.exit(1)
    
    lineno = obj.get("lineno")
    if lineno is None or not isinstance(lineno, int):
        print(f"ERROR: Line {i}: lineno missing or not int", file=sys.stderr)
        sys.exit(1)
    linenos.add(lineno)

if linenos != {1, 3}:
    print(f"ERROR: linenos should be {{1, 3}}, got {linenos}", file=sys.stderr)
    sys.exit(1)

print("[signals_dump_smoke] Assertion 4 passed: All lines parse as valid JSON with required fields")
PYTHON

echo "[signals_dump_smoke] OK ✅" >&2
