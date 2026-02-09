#!/bin/bash
# scripts/ml_trigger_smoke.sh
# Integration smoke test for ML Retraining Trigger Logic

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() {
  echo -e "${RED}[ml_trigger_smoke] FAIL: $*${NC}" >&2
  exit 1
}

pass() {
  echo -e "${GREEN}[ml_trigger_smoke] OK: $*${NC}" >&2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="${ROOT_DIR}/integration/fixtures/ml_trigger"

echo "[ml_trigger_smoke] Testing ML Retraining Trigger..." >&2

# Test 1: Pure logic tests (Cadence)
echo "[ml_trigger_smoke] Testing Cadence Trigger..." >&2

python3 << 'PYEOF'
import sys
sys.path.insert(0, "${ROOT_DIR}")

from strategy.ml_trigger import check_cadence

# Test: Cadence not expired (12 hours, threshold 24)
expired, details = check_cadence(1700000000, 1700000000 + 12*3600, 24)
assert expired == False, f"Expected False, got {expired}"
assert abs(details["hours_since"] - 12.0) < 0.01, f"Expected 12.0, got {details['hours_since']}"
print("Cadence not expired: PASS")

# Test: Cadence expired (48 hours, threshold 24)
expired, details = check_cadence(1700000000, 1700000000 + 48*3600, 24)
assert expired == True, f"Expected True, got {expired}"
assert abs(details["hours_since"] - 48.0) < 0.01, f"Expected 48.0, got {details['hours_since']}"
print("Cadence expired: PASS")

print("Cadence Trigger: PASS")
PYEOF

pass "Testing Cadence Trigger"

# Test 2: Pure logic tests (PSI)
echo "[ml_trigger_smoke] Testing PSI Calculation..." >&2

python3 << 'PYEOF'
import sys
sys.path.insert(0, "${ROOT_DIR}")

from strategy.ml_trigger import compute_feature_psi

# Test: Identical distributions should have PSI ~ 0
baseline = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
current = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
psi = compute_feature_psi(baseline, current, num_buckets=5)
assert psi < 0.1, f"Expected low PSI for identical distributions, got {psi}"
print(f"Identical distributions PSI: {psi:.4f} (expected low)")

# Test: Different distributions should have higher PSI
baseline = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
current = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
psi = compute_feature_psi(baseline, current, num_buckets=5)
assert psi > 0.5, f"Expected high PSI for different distributions, got {psi}"
print(f"Different distributions PSI: {psi:.4f} (expected high)")

print("PSI Calculation: PASS")
PYEOF

pass "Testing PSI Calculation"

# Test 3: Drift trigger test (with fixed timestamp to avoid time-based failures)
echo "[ml_trigger_smoke] Testing Drift Trigger..." >&2

# Use a timestamp close enough to last_train that cadence won't trigger
# Last train: 1700000000
# Now: 1700000000 + 12 hours = cadence not expired
NOW_TS=$((1700000000 + 12*3600))

# Run with stable features (should NOT trigger drift)
echo "[ml_trigger_smoke] Testing with stable features..." >&2
STABLE_OUTPUT=$(cd "${ROOT_DIR}" && python3 -m integration.ml_retraining_check \
    --metadata "${FIXTURE_DIR}/model_metadata.json" \
    --current "${FIXTURE_DIR}/features_stable.jsonl" \
    --config "${FIXTURE_DIR}/config.yaml" \
    --now ${NOW_TS} 2>&1)

echo "[ml_trigger_smoke] Stable output: ${STABLE_OUTPUT}" >&2

# Verify stable output (should NOT have drift_detected if PSI is low)
STABLE_TRIGGER=$(echo "${STABLE_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['trigger'])")
STABLE_REASONS=$(echo "${STABLE_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['reasons'])")

echo "[ml_trigger_smoke] Stable: trigger=${STABLE_TRIGGER}, reasons=${STABLE_REASONS}" >&2

# Test 4: Drift trigger test with drifted features
echo "[ml_trigger_smoke] Testing with drifted features..." >&2
DRIFTED_OUTPUT=$(cd "${ROOT_DIR}" && python3 -m integration.ml_retraining_check \
    --metadata "${FIXTURE_DIR}/model_metadata.json" \
    --current "${FIXTURE_DIR}/features_drifted.jsonl" \
    --config "${FIXTURE_DIR}/config.yaml" \
    --now ${NOW_TS} 2>&1)

echo "[ml_trigger_smoke] Drifted output: ${DRIFTED_OUTPUT}" >&2

# Verify drifted output
DRIFTED_TRIGGER=$(echo "${DRIFTED_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['trigger'])")
DRIFTED_REASONS=$(echo "${DRIFTED_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['reasons'])")
DRIFTED_MAX_PSI=$(echo "${DRIFTED_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['metrics']['max_psi'])")

echo "[ml_trigger_smoke] Drifted: trigger=${DRIFTED_TRIGGER}, reasons=${DRIFTED_REASONS}, max_psi=${DRIFTED_MAX_PSI}" >&2

# Verify results
python3 << 'PYEOF'
import json
import sys

# Parse outputs
stable_output = """${STABLE_OUTPUT}"""
drifted_output = """${DRIFTED_OUTPUT}"""

# Verify JSON is valid
try:
    stable_result = json.loads(stable_output)
    drifted_result = json.loads(drifted_output)
    print("Both outputs are valid JSON: PASS")
except json.JSONDecodeError as e:
    print(f"Invalid JSON: {e}")
    sys.exit(1)

# Verify required fields
for result, name in [(stable_result, "stable"), (drifted_result, "drifted")]:
    assert "trigger" in result, f"Missing 'trigger' in {name} output"
    assert "reasons" in result, f"Missing 'reasons' in {name} output"
    assert "metrics" in result, f"Missing 'metrics' in {name} output"
    assert "max_psi" in result["metrics"], f"Missing 'max_psi' in {name} metrics"
    print(f"Required fields present in {name}: PASS")

print("Output Schema Validation: PASS")
PYEOF

# Verify drift detection
if echo "${DRIFTED_REASONS}" | grep -q "drift_detected"; then
    pass "Drift detection triggered correctly"
else
    fail "Drift detection should have triggered for drifted features"
fi

# Test 5: Cadence trigger test
echo "[ml_trigger_smoke] Testing Cadence Trigger with CLI..." >&2

# Use a timestamp far enough that cadence WILL trigger
# Last train: 1700000000
# Now: 1700000000 + 48 hours = cadence expired
NOW_TS=$((1700000000 + 48*3600))

CADENCE_OUTPUT=$(cd "${ROOT_DIR}" && python3 -m integration.ml_retraining_check \
    --metadata "${FIXTURE_DIR}/model_metadata.json" \
    --current "${FIXTURE_DIR}/features_stable.jsonl" \
    --config "${FIXTURE_DIR}/config.yaml" \
    --now ${NOW_TS} 2>&1)

echo "[ml_trigger_smoke] Cadence output: ${CADENCE_OUTPUT}" >&2

CADENCE_TRIGGER=$(echo "${CADENCE_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['trigger'])")
CADENCE_REASONS=$(echo "${CADENCE_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['reasons'])")

if echo "${CADENCE_REASONS}" | grep -q "cadence_expired"; then
    pass "Cadence trigger triggered correctly"
else
    fail "Cadence trigger should have triggered for expired cadence"
fi

echo "[ml_trigger_smoke] All tests passed!" >&2
echo -e "${GREEN}[ml_trigger_smoke] OK ✅${NC}" >&2

exit 0
