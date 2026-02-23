#!/bin/bash
# scripts/grafana_export_smoke.sh
# Smoke test for Grafana Datasource Adapter

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail() {
  echo -e "${RED}[grafana_export_smoke] FAIL: $*${NC}" >&2
  exit 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[overlay_lint] running grafana export smoke..." >&2

# Test 1: Metrics conversion
echo "[grafana_export_smoke] Validating Metrics conversion..." >&2

METRICS_OUTPUT=$(python3 "${ROOT_DIR}/integration/tools/export_grafana.py" \
  --input "${ROOT_DIR}/integration/fixtures/monitoring/metrics_sample.json" \
  --type metrics 2>&1)

# Check output contains expected patterns
if ! echo "$METRICS_OUTPUT" | grep -q "strategy_metrics"; then
  fail "Metrics output missing measurement name"
fi

if ! echo "$METRICS_OUTPUT" | grep -q "mode=paper"; then
  fail "Metrics output missing mode=paper tag"
fi

if ! echo "$METRICS_OUTPUT" | grep -q "roi_p50=12.5"; then
  fail "Metrics output missing flattened roi_p50 field"
fi

if ! echo "$METRICS_OUTPUT" | grep -q "risk_drawdown=5"; then
  fail "Metrics output missing flattened risk_drawdown field"
fi

echo "[grafana_export_smoke] Validating Metrics conversion... PASS" >&2

# Test 2: Signals conversion
echo "[grafana_export_smoke] Validating Signals conversion..." >&2

SIGNALS_OUTPUT=$(python3 "${ROOT_DIR}/integration/tools/export_grafana.py" \
  --input "${ROOT_DIR}/integration/fixtures/monitoring/signals_sample.jsonl" \
  --type signals 2>&1)

# Count output lines
OUTPUT_LINES=$(echo "$SIGNALS_OUTPUT" | wc -l)
INPUT_LINES=3

if [ "$OUTPUT_LINES" -ne "$INPUT_LINES" ]; then
  fail "Signals output has $OUTPUT_LINES lines, expected $INPUT_LINES"
fi

# Check each signal appears
for signal_id in "sig-001" "sig-002" "sig-003"; do
  if ! echo "$SIGNALS_OUTPUT" | grep -q "$signal_id"; then
    fail "Signals output missing $signal_id"
  fi
done

# Check symbol appears
if ! echo "$SIGNALS_OUTPUT" | grep -q "SOL/USDC"; then
  fail "Signals output missing SOL/USDC symbol"
fi

echo "[grafana_export_smoke] Validating Signals conversion... PASS" >&2

# Test 3: Verify InfluxDB Line Protocol format
echo "[grafana_export_smoke] Verifying InfluxDB Line Protocol format..." >&2

# Check format: measurement,tag_set field_set timestamp
# Pattern: name,key=value key=value timestamp
if ! echo "$METRICS_OUTPUT" | grep -qE "^[a-zA-Z0-9_]+,.* [a-zA-Z0-9_]+=.* [0-9]+$"; then
  fail "Metrics output does not match InfluxDB Line Protocol format"
fi

echo "[grafana_export_smoke] Verifying InfluxDB Line Protocol format... PASS" >&2

# Test 4: Determinism
echo "[grafana_export_smoke] Verifying determinism..." >&2

METRICS_OUTPUT2=$(python3 "${ROOT_DIR}/integration/tools/export_grafana.py" \
  --input "${ROOT_DIR}/integration/fixtures/monitoring/metrics_sample.json" \
  --type metrics 2>/dev/null)

if [ "$METRICS_OUTPUT" != "$METRICS_OUTPUT2" ]; then
  fail "Metrics conversion is not deterministic"
fi

echo "[grafana_export_smoke] Verifying determinism... PASS" >&2

echo -e "${GREEN}[grafana_export_smoke] OK ✅${NC}" >&2

exit 0
