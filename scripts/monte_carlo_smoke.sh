#!/bin/bash
# scripts/monte_carlo_smoke.sh
# Smoke test for Monte Carlo Harness

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail() {
  echo -e "${RED}[monte_carlo_smoke] FAIL: $*${NC}" >&2
  exit 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[overlay_lint] running monte carlo smoke..." >&2

# Test: Run Monte Carlo with 10 iterations
echo "[monte_carlo_smoke] Testing Monte Carlo harness with 10 iterations..." >&2

OUTPUT=$(python3 "${ROOT_DIR}/integration/monte_carlo.py" \
  --trades "${ROOT_DIR}/integration/fixtures/monte_carlo/trades.jsonl" \
  --config "${ROOT_DIR}/integration/fixtures/monte_carlo/config.yaml" \
  --runs 10 \
  --seed 42 \
  --quiet 2>/dev/null)

# Check if output contains valid JSON with p50
echo "[monte_carlo_smoke] Checking output..." >&2

# Verify JSON output
if ! echo "$OUTPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'p50' in d.get('roi_pct', {})" 2>/dev/null; then
  fail "Output JSON missing required p50 field"
fi

# Verify runs count
if ! echo "$OUTPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); assert d.get('runs', 0) == 10" 2>/dev/null; then
  fail "Output JSON runs count mismatch"
fi

# Verify win_prob exists
if ! echo "$OUTPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'win_prob' in d" 2>/dev/null; then
  fail "Output JSON missing win_prob field"
fi

# Verify deterministic with same seed
echo "[monte_carlo_smoke] Verifying determinism..." >&2
OUTPUT2=$(python3 "${ROOT_DIR}/integration/monte_carlo.py" \
  --trades "${ROOT_DIR}/integration/fixtures/monte_carlo/trades.jsonl" \
  --config "${ROOT_DIR}/integration/fixtures/monte_carlo/config.yaml" \
  --runs 10 \
  --seed 42 \
  --quiet 2>/dev/null)

if [ "$OUTPUT" != "$OUTPUT2" ]; then
  fail "Same seed should produce identical output"
fi

echo "[monte_carlo_smoke] Output JSON:" >&2
echo "$OUTPUT" >&2

echo -e "${GREEN}[monte_carlo_smoke] OK ✅${NC}" >&2

exit 0
