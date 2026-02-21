#!/bin/bash
#
# Survival Analysis Smoke Test
# Validates hazard score calculation interface and basic functionality
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEIGHTS_FILE="$PROJECT_ROOT/integration/fixtures/ml_trigger/survival_weights.json"
PYTHON_PATH="$PROJECT_ROOT"

echo "[survival_smoke] Running survival analysis smoke tests..."

# Check if weights file exists
if [ ! -f "$WEIGHTS_FILE" ]; then
    echo "[survival_smoke] ERROR: weights file not found at $WEIGHTS_FILE" >&2
    exit 1
fi

# Add project root to PYTHONPATH
export PYTHONPATH="$PYTHON_PATH:$PYTHONPATH"

PASS_COUNT=0
FAIL_COUNT=0

# Test Case 1: Safe scenario
# smart_money_exit_count=0, duration=10s -> expected hazard < 0.2
echo "[survival_smoke] Case Safe..." >&2
safe_result=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.survival import SurvivalEstimator

estimator = SurvivalEstimator('$WEIGHTS_FILE')
features = {
    'volatility_z_score': 0.5,
    'smart_money_exit_count': 0,
    'volume_delta_pct': -0.1
}
hazard = estimator.predict_hazard(features, 10.0)
verdict = estimator.get_verdict(hazard)
print(f'{hazard:.2f}:{verdict}')
" 2>&1) || {
    echo "[survival_smoke] Case Safe: ERROR - $safe_result" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    exit 1
}

safe_hazard=$(echo "$safe_result" | cut -d':' -f1)
safe_verdict=$(echo "$safe_result" | cut -d':' -f2)

if python3 -c "import sys; sys.exit(0 if float("$safe_hazard") < 0.2 else 1)" && [ "$safe_verdict" = "HOLD" ]; then
    echo "[survival_smoke] Case Safe: Hazard=$safe_hazard -> $safe_verdict"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "[survival_smoke] Case Safe: FAIL - Hazard=$safe_hazard (expected < 0.2), Verdict=$safe_verdict (expected HOLD)" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Test Case 2: Danger scenario
# smart_money_exit_count=5, duration=300s -> expected hazard > 0.8
echo "[survival_smoke] Case Danger..." >&2
danger_result=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.survival import SurvivalEstimator

estimator = SurvivalEstimator('$WEIGHTS_FILE')
features = {
    'volatility_z_score': 3.0,
    'smart_money_exit_count': 5,
    'volume_delta_pct': 2.0
}
hazard = estimator.predict_hazard(features, 300.0)
verdict = estimator.get_verdict(hazard)
print(f'{hazard:.2f}:{verdict}')
" 2>&1) || {
    echo "[survival_smoke] Case Danger: ERROR - $danger_result" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    exit 1
}

danger_hazard=$(echo "$danger_result" | cut -d':' -f1)
danger_verdict=$(echo "$danger_result" | cut -d':' -f2)

if python3 -c "import sys; sys.exit(0 if float("$danger_hazard") > 0.8 else 1)" && [ "$danger_verdict" = "EXIT" ]; then
    echo "[survival_smoke] Case Danger: Hazard=$danger_hazard -> $danger_verdict"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "[survival_smoke] Case Danger: FAIL - Hazard=$danger_hazard (expected > 0.8), Verdict=$danger_verdict (expected EXIT)" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Test Case 3: Weights loading from fixture
echo "[survival_smoke] Case Weights Loading..." >&2
weights_test=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.survival import SurvivalEstimator

estimator = SurvivalEstimator('$WEIGHTS_FILE')
# Check that custom weights are loaded
w = estimator.weights['weights']
print(f'{w[\"smart_money_exit_count\"]}:{w[\"volatility_z_score\"]}')
" 2>&1) || {
    echo "[survival_smoke] Case Weights Loading: ERROR - $weights_test" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    exit 1
}

sm_exit_w=$(echo "$weights_test" | cut -d':' -f1)
vol_w=$(echo "$weights_test" | cut -d':' -f2)

if [ "$sm_exit_w" = "0.5" ] && [ "$vol_w" = "0.2" ]; then
    echo "[survival_smoke] Case Weights Loading: PASS"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "[survival_smoke] Case Weights Loading: FAIL - weights=$weights_test (expected smart_money_exit=0.5, volatility=0.2)" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Test Case 4: should_exit function
echo "[survival_smoke] Case Should Exit..." >&2
exit_test=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.survival import SurvivalEstimator

estimator = SurvivalEstimator('$WEIGHTS_FILE')
# Test with high hazard
high_hazard = estimator.predict_hazard({'smart_money_exit_count': 10}, 600.0)
high_exit = estimator.should_exit(high_hazard, 0.7)
# Test with low hazard
low_hazard = estimator.predict_hazard({'smart_money_exit_count': 0}, 10.0)
low_exit = estimator.should_exit(low_hazard, 0.7)
print(f'{high_exit}:{low_exit}')
" 2>&1) || {
    echo "[survival_smoke] Case Should Exit: ERROR - $exit_test" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    exit 1
}

high_exit=$(echo "$exit_test" | cut -d':' -f1)
low_exit=$(echo "$exit_test" | cut -d':' -f2)

if [ "$high_exit" = "True" ] && [ "$low_exit" = "False" ]; then
    echo "[survival_smoke] Case Should Exit: PASS"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "[survival_smoke] Case Should Exit: FAIL - high_exit=$high_exit (expected True), low_exit=$low_exit (expected False)" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Summary
echo "[survival_smoke] Results: $PASS_COUNT passed, $FAIL_COUNT failed"

if [ $FAIL_COUNT -eq 0 ]; then
    echo "[survival_smoke] OK"
    exit 0
else
    echo "[survival_smoke] FAIL" >&2
    exit 1
fi
