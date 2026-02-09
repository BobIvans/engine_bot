#!/usr/bin/env bash
set -euo pipefail

# scripts/execution_preflight_smoke.sh
# Smoke test for PR-6.1 execution preflight layer

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Run the paper pipeline with execution_preflight enabled
OUTPUT=$(python3 -m integration.paper_pipeline --dry-run --summary-json --execution-preflight \
  --config integration/fixtures/config/execution_preflight.yaml \
  --allowlist strategy/wallet_allowlist.yaml \
  --token-snapshot integration/fixtures/token_snapshot.execution_preflight.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.execution_preflight.csv \
  --trades-jsonl integration/fixtures/trades.execution_preflight.jsonl \
  2>/dev/null)

# Assertions:
# 1) stdout exactly 1 line
if [[ -z "$OUTPUT" ]]; then
  echo "ERROR: execution_preflight_smoke: no output" >&2
  exit 1
fi

# Count lines - should be exactly 1
LINE_COUNT=$(echo "$OUTPUT" | wc -l)
if [[ "$LINE_COUNT" -ne 1 ]]; then
  echo "ERROR: execution_preflight_smoke: expected 1 line, got $LINE_COUNT" >&2
  exit 1
fi

# 2) JSON parses with execution_metrics key
if ! echo "$OUTPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); 'execution_metrics' in d" 2>/dev/null; then
  echo "ERROR: execution_preflight_smoke: JSON missing execution_metrics key" >&2
  exit 1
fi

# 3) schema_version == "execution_metrics.v1"
SCHEMA=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['execution_metrics']['schema_version'])")
if [[ "$SCHEMA" != "execution_metrics.v1" ]]; then
  echo "ERROR: execution_preflight_smoke: expected schema_version 'execution_metrics.v1', got '$SCHEMA'" >&2
  exit 1
fi

# 4) candidates == 2
CANDIDATES=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['execution_metrics']['candidates'])")
if [[ "$CANDIDATES" -ne 2 ]]; then
  echo "ERROR: execution_preflight_smoke: expected candidates=2, got $CANDIDATES" >&2
  exit 1
fi

# 5) filled == 1
FILLED=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['execution_metrics']['filled'])")
if [[ "$FILLED" -ne 1 ]]; then
  echo "ERROR: execution_preflight_smoke: expected filled=1, got $FILLED" >&2
  exit 1
fi

# 6) fill_rate == 0.5
FILL_RATE=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['execution_metrics']['fill_rate'])")
if [[ "$(echo "$FILL_RATE == 0.5" | bc -l)" -ne 1 ]]; then
  echo "ERROR: execution_preflight_smoke: expected fill_rate=0.5, got $FILL_RATE" >&2
  exit 1
fi

# 7) fill_fail_by_reason.slippage_too_high == 1
SLIPPAGE_FAIL=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['execution_metrics']['fill_fail_by_reason']['slippage_too_high'])")
if [[ "$SLIPPAGE_FAIL" -ne 1 ]]; then
  echo "ERROR: execution_preflight_smoke: expected slippage_too_high=1, got $SLIPPAGE_FAIL" >&2
  exit 1
fi

echo "[execution_preflight] OK ✅" >&2
