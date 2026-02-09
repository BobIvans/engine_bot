#!/bin/bash
# Smoke test for Co-Trade Timing Analysis
# Tests: pure logic, CLI integration, lag calculations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/timing"
OUTPUT_FILE="/tmp/timing_output.json"

echo "[timing_analysis_smoke] Starting timing analysis smoke test..."

# Clean up any previous output
rm -f "$OUTPUT_FILE"

# Test 1: Run timing analysis CLI
echo "[timing_analysis_smoke] Running timing analysis on fixture..."
python3 -m integration.timing_analysis \
    --trades "$FIXTURE_DIR/trades.jsonl" \
    --out "$OUTPUT_FILE" \
    --verbose

# Test 2: Verify output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "[timing_analysis_smoke] FAIL: Output file not created"
    exit 1
fi

# Test 3: Verify output contains expected wallets
echo "[timing_analysis_smoke] Verifying output format..."
WALLETS=$(python3 -c "import json; print(' '.join(json.load(open('$OUTPUT_FILE'))['wallets'].keys()))")

if [[ ! "$WALLETS" =~ "W1" ]]; then
    echo "[timing_analysis_smoke] FAIL: W1 not found in output"
    exit 1
fi

if [[ ! "$WALLETS" =~ "W2" ]]; then
    echo "[timing_analysis_smoke] FAIL: W2 not found in output"
    exit 1
fi

if [[ ! "$WALLETS" =~ "W3" ]]; then
    echo "[timing_analysis_smoke] FAIL: W3 not found in output"
    exit 1
fi

# Test 4: Verify W1 has avg_lag = 0.0 (W1 is leader for both tokens)
echo "[timing_analysis_smoke] Verifying W1 avg_lag (should be 0.0)..."
AVG_LAG_W1=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['wallets']['W1']['avg_lag_sec'])")

if (( $(echo "$AVG_LAG_W1 != 0.0" | bc -l) )); then
    echo "[timing_analysis_smoke] FAIL: W1 avg_lag should be 0.0, got $AVG_LAG_W1"
    exit 1
fi

# Test 5: Verify W2 has avg_lag = 5.0 (only entry is 5s after W1)
echo "[timing_analysis_smoke] Verifying W2 avg_lag (should be 5.0)..."
AVG_LAG_W2=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['wallets']['W2']['avg_lag_sec'])")

if (( $(echo "$AVG_LAG_W2 != 5.0" | bc -l) )); then
    echo "[timing_analysis_smoke] FAIL: W2 avg_lag should be 5.0, got $AVG_LAG_W2"
    exit 1
fi

# Test 6: Verify W3 has avg_lag = 6.0 ((10+2)/2 = 6.0)
echo "[timing_analysis_smoke] Verifying W3 avg_lag (should be 6.0)..."
AVG_LAG_W3=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['wallets']['W3']['avg_lag_sec'])")

if (( $(echo "$AVG_LAG_W3 != 6.0" | bc -l) )); then
    echo "[timing_analysis_smoke] FAIL: W3 avg_lag should be 6.0, got $AVG_LAG_W3"
    exit 1
fi

# Test 7: Verify first_mover_ratio
echo "[timing_analysis_smoke] Verifying first_mover_ratio..."
W1_RATIO=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['wallets']['W1']['first_mover_ratio'])")
W2_RATIO=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['wallets']['W2']['first_mover_ratio'])")

if (( $(echo "$W1_RATIO != 1.0" | bc -l) )); then
    echo "[timing_analysis_smoke] FAIL: W1 first_mover_ratio should be 1.0, got $W1_RATIO"
    exit 1
fi

if (( $(echo "$W2_RATIO != 0.0" | bc -l) )); then
    echo "[timing_analysis_smoke] FAIL: W2 first_mover_ratio should be 0.0, got $W2_RATIO"
    exit 1
fi

# Test 8: Verify version format
echo "[timing_analysis_smoke] Verifying output version format..."
VERSION=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['version'])")

if [[ "$VERSION" != "timing_distribution.v1" ]]; then
    echo "[timing_analysis_smoke] FAIL: Expected version 'timing_distribution.v1', got '$VERSION'"
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_FILE"

echo "[timing_analysis_smoke] All timing analysis tests passed!"
echo "[timing_analysis_smoke] OK"
