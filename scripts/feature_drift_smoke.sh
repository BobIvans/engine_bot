#!/bin/bash
# Smoke test for Feature Drift Detection
# Tests: PSI calculation, CLI integration, drift detection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/drift"
OUTPUT_NORMAL="/tmp/drift_normal.json"
OUTPUT_DRIFT="/tmp/drift_drift.json"

echo "[feature_drift_smoke] Starting feature drift smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_NORMAL" "$OUTPUT_DRIFT"

# Test 1: Run drift detection on normal (no drift) data
echo "[feature_drift_smoke] Running drift detection on normal data..." >&2
python3 -m integration.feature_drift_stage \
    --baseline "$FIXTURE_DIR/baseline_stats.json" \
    --current "$FIXTURE_DIR/current_features_normal.jsonl" \
    --out "$OUTPUT_NORMAL" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_NORMAL" ]; then
    echo "[feature_drift_smoke] FAIL: Normal output file not created" >&2
    exit 1
fi

# Verify normal case has OK status
echo "[feature_drift_smoke] Verifying normal case status..." >&2
STATUS_NORMAL=$(python3 -c "import json; print(json.load(open('$OUTPUT_NORMAL'))['global_status'])")
if [ "$STATUS_NORMAL" != "OK" ]; then
    echo "[feature_drift_smoke] FAIL: Expected OK status for normal data, got $STATUS_NORMAL" >&2
    exit 1
fi

# Verify normal case PSI is low
PSI_NORMAL=$(python3 -c "import json; print(json.load(open('$OUTPUT_NORMAL'))['features']['feature_A'])")
PSI_CHECK=$(python3 -c "print('OK' if $PSI_NORMAL < 0.1 else 'FAIL')")
if [ "$PSI_CHECK" != "OK" ]; then
    echo "[feature_drift_smoke] FAIL: Normal case PSI should be < 0.1, got $PSI_NORMAL" >&2
    exit 1
fi
echo "[feature_drift_smoke] Normal case: PSI=$PSI_NORMAL, status=$STATUS_NORMAL" >&2

# Test 2: Run drift detection on drifted data
echo "[feature_drift_smoke] Running drift detection on drifted data..." >&2
python3 -m integration.feature_drift_stage \
    --baseline "$FIXTURE_DIR/baseline_stats.json" \
    --current "$FIXTURE_DIR/current_features_drift.jsonl" \
    --out "$OUTPUT_DRIFT" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_DRIFT" ]; then
    echo "[feature_drift_smoke] FAIL: Drift output file not created" >&2
    exit 1
fi

# Verify drift case has CRITICAL status
echo "[feature_drift_smoke] Verifying drift case status..." >&2
STATUS_DRIFT=$(python3 -c "import json; print(json.load(open('$OUTPUT_DRIFT'))['global_status'])")
if [ "$STATUS_DRIFT" != "CRITICAL" ]; then
    echo "[feature_drift_smoke] FAIL: Expected CRITICAL status for drifted data, got $STATUS_DRIFT" >&2
    exit 1
fi

# Verify drift case PSI is high (> 0.25)
PSI_DRIFT=$(python3 -c "import json; print(json.load(open('$OUTPUT_DRIFT'))['features']['feature_A'])")
PSI_DRIFT_CHECK=$(python3 -c "print('OK' if $PSI_DRIFT > 0.25 else 'FAIL')")
if [ "$PSI_DRIFT_CHECK" != "OK" ]; then
    echo "[feature_drift_smoke] FAIL: Drift case PSI should be > 0.25, got $PSI_DRIFT" >&2
    exit 1
fi
echo "[feature_drift_smoke] Drift case: PSI=$PSI_DRIFT, status=$STATUS_DRIFT" >&2

# Test 3: Verify output version format
echo "[feature_drift_smoke] Verifying output version format..." >&2
VERSION=$(python3 -c "import json; print(json.load(open('$OUTPUT_DRIFT'))['version'])")
if [ "$VERSION" != "drift_report.v1" ]; then
    echo "[feature_drift_smoke] FAIL: Expected version 'drift_report.v1', got '$VERSION'" >&2
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_NORMAL" "$OUTPUT_DRIFT"

echo "[feature_drift_smoke] All drift detection tests passed!" >&2
echo "[feature_drift_smoke] OK ✅"
