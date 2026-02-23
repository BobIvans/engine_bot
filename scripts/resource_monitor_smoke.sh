#!/bin/bash
# Smoke test for Free-Tier Resource Monitor
# Tests: quota checking, status thresholds, alert generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/resource_monitor"
OUTPUT_SAFE="/tmp/resource_status_safe.json"
OUTPUT_CRITICAL="/tmp/resource_status_critical.json"

echo "[resource_monitor_smoke] Starting resource monitor smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_SAFE" "$OUTPUT_CRITICAL"

# Test 1: Run with safe usage (should be OK)
echo "[resource_monitor_smoke] Running with safe usage..." >&2
python3 -m integration.resource_monitor_stage \
    --usage "$FIXTURE_DIR/usage_safe.json" \
    --limits "$FIXTURE_DIR/limits.yaml" \
    --out "$OUTPUT_SAFE" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_SAFE" ]; then
    echo "[resource_monitor_smoke] FAIL: Safe output file not created" >&2
    exit 1
fi

# Verify safe case has OK status
echo "[resource_monitor_smoke] Verifying safe case status..." >&2
STATUS_SAFE=$(python3 -c "import json; print(json.load(open('$OUTPUT_SAFE'))['global_status'])")
if [ "$STATUS_SAFE" != "OK" ]; then
    echo "[resource_monitor_smoke] FAIL: Expected OK status for safe data, got $STATUS_SAFE" >&2
    exit 1
fi
echo "[resource_monitor_smoke] Safe case: global_status=$STATUS_SAFE ✓" >&2

# Test 2: Run with critical usage (should be CRITICAL)
echo "[resource_monitor_smoke] Running with critical usage..." >&2
python3 -m integration.resource_monitor_stage \
    --usage "$FIXTURE_DIR/usage_critical.json" \
    --limits "$FIXTURE_DIR/limits.yaml" \
    --out "$OUTPUT_CRITICAL" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_CRITICAL" ]; then
    echo "[resource_monitor_smoke] FAIL: Critical output file not created" >&2
    exit 1
fi

# Verify critical case has CRITICAL status
echo "[resource_monitor_smoke] Verifying critical case status..." >&2
STATUS_CRITICAL=$(python3 -c "import json; print(json.load(open('$OUTPUT_CRITICAL'))['global_status'])")
if [ "$STATUS_CRITICAL" != "CRITICAL" ]; then
    echo "[resource_monitor_smoke] FAIL: Expected CRITICAL for exceeded data, got $STATUS_CRITICAL" >&2
    exit 1
fi
echo "[resource_monitor_smoke] Critical case: global_status=$STATUS_CRITICAL ✓" >&2

# Test 3: Verify alerts are generated for critical case
echo "[resource_monitor_smoke] Verifying alerts generation..." >&2
ALERTS_COUNT=$(python3 -c "import json; print(len(json.load(open('$OUTPUT_CRITICAL'))['alerts']))")
if [ "$ALERTS_COUNT" -lt 1 ]; then
    echo "[resource_monitor_smoke] FAIL: Expected alerts for critical case, got $ALERTS_COUNT" >&2
    exit 1
fi
echo "[resource_monitor_smoke] Critical case has $ALERTS_COUNT alerts ✓" >&2

# Test 4: Verify version format
echo "[resource_monitor_smoke] Verifying output version format..." >&2
VERSION=$(python3 -c "import json; print(json.load(open('$OUTPUT_SAFE'))['version'])")
if [ "$VERSION" != "resource_status.v1" ]; then
    echo "[resource_monitor_smoke] FAIL: Expected version 'resource_status.v1', got '$VERSION'" >&2
    exit 1
fi

# Test 5: Verify utilization percentages are calculated
echo "[resource_monitor_smoke] Verifying utilization calculations..." >&2
UTIL_PCT=$(python3 -c "
import json
data = json.load(open('$OUTPUT_SAFE'))
rpc = data['details'].get('rpc_requests_today', {})
print(rpc.get('utilization_pct', -1))
")
if python3 -c "import sys; u=float(sys.argv[1]); sys.exit(0 if (u > 0 and u < 100) else 1)" "$UTIL_PCT"; then
    echo "[resource_monitor_smoke] Utilization percentage calculated: $UTIL_PCT% ✓" >&2
else
    echo "[resource_monitor_smoke] FAIL: Invalid utilization percentage: $UTIL_PCT" >&2
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_SAFE" "$OUTPUT_CRITICAL"

echo "[resource_monitor_smoke] All resource monitor tests passed!" >&2
echo "[resource_monitor_smoke] OK ✅"
