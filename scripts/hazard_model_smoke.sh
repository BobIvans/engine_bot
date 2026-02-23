#!/usr/bin/env bash
#
# scripts/hazard_model_smoke.sh
#
# PR-ML.4 Smoke Test for Hazard Model
# Validates survival analysis model scoring and calibration
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "[${YELLOW}hazard_model_smoke${NC}] Starting hazard model smoke test..."

# Test 1: Verify survival_model.py exists and is importable
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 1: Importing survival_model.py..."
cd "$ROOT_DIR"
python3 -c "
from analysis.survival_model import compute_hazard_score, is_emergency_exit, calibrate_hazard_score
print('[hazard_model_smoke] survival_model.py imports OK')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] survival_model.py import failed"
    exit 1
}

# Test 2: Verify hazard_calibrator.py exists and is importable
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 2: Importing hazard_calibrator.py..."
python3 -c "
from integration.models.hazard_calibrator import load_hazard_calibration, get_default_calibration
print('[hazard_model_smoke] hazard_calibrator.py imports OK')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] hazard_calibrator.py import failed"
    exit 1
}

# Test 3: Verify schema exists
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 3: Checking hazard_score_schema.json..."
SCHEMA_FILE="$ROOT_DIR/strategy/schemas/hazard_score_schema.json"
if [[ -f "$SCHEMA_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] hazard_score_schema.json exists"
else
    echo -e "[${RED}FAIL${NC}] hazard_score_schema.json not found"
    exit 1
fi

# Test 4: Verify fixture exists
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 4: Checking hazard_training_sample.json..."
FIXTURE_FILE="$ROOT_DIR/integration/fixtures/ml/hazard_training_sample.json"
if [[ -f "$FIXTURE_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] hazard_training_sample.json exists"
else
    echo -e "[${RED}FAIL${NC}] hazard_training_sample.json not found"
    exit 1
fi

# Test 5: Run hazard scoring on sample data
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 5: Running hazard scoring on sample data..."
if ! python3 - <<'PY' 2>/dev/null
import json
from analysis.survival_model import compute_hazard_score, is_emergency_exit

# Load training sample
with open('integration/fixtures/ml/hazard_training_sample.json') as f:
    data = json.load(f)

# Test crash case (high hazard)
crash_features = {
    'liquidity_drop_10s': 0.92,
    'top_holder_sell_ratio': 0.85,
    'mint_auth_exists': 1.0,
    'cluster_sell_pressure': 0.78,
    'pmkt_event_risk': 0.45,
    'time_since_launch_hours': 2.5
}

# Test survivor case (low hazard)
survivor_features = {
    'liquidity_drop_10s': 0.05,
    'top_holder_sell_ratio': 0.08,
    'mint_auth_exists': 0.0,
    'cluster_sell_pressure': 0.05,
    'pmkt_event_risk': 0.10,
    'time_since_launch_hours': 120.0
}

# Compute hazard scores
crash_score = compute_hazard_score(crash_features)
survivor_score = compute_hazard_score(survivor_features)

# Verify crash score is higher
if crash_score > survivor_score:
    print(f'[hazard_model_smoke] Crash score ({crash_score:.3f}) > Survivor score ({survivor_score:.3f}): OK')
else:
    print(f'[hazard_model_smoke] FAIL: Crash score ({crash_score:.3f}) should be > Survivor score ({survivor_score:.3f})')
    exit(1)

# Test emergency exit trigger
if is_emergency_exit(crash_score, hazard_threshold=0.65):
    print(f'[hazard_model_smoke] Emergency exit triggered for crash (score={crash_score:.3f}): OK')
else:
    print(f'[hazard_model_smoke] FAIL: Emergency exit should trigger for crash (score={crash_score:.3f})')
    exit(1)

if not is_emergency_exit(survivor_score, hazard_threshold=0.65):
    print(f'[hazard_model_smoke] No emergency exit for survivor (score={survivor_score:.3f}): OK')
else:
    print(f'[hazard_model_smoke] FAIL: No emergency exit for survivor (score={survivor_score:.3f})')
    exit(1)

# Test on all training samples
crash_scores = []
survivor_scores = []
for trade in data['trades']:
    features = {
        'liquidity_drop_10s': trade['liquidity_drop_10s'],
        'top_holder_sell_ratio': trade['top_holder_sell_ratio'],
        'mint_auth_exists': trade['mint_auth_exists'],
        'cluster_sell_pressure': trade['cluster_sell_pressure'],
        'pmkt_event_risk': trade['pmkt_event_risk'],
        'time_since_launch_hours': trade['time_since_launch_hours']
    }
    score = compute_hazard_score(features)
    if trade['is_crash']:
        crash_scores.append(score)
    else:
        survivor_scores.append(score)

avg_crash = sum(crash_scores) / len(crash_scores)
avg_survivor = sum(survivor_scores) / len(survivor_scores)

print(f'[hazard_model_smoke] Avg crash score: {avg_crash:.3f}')
print(f'[hazard_model_smoke] Avg survivor score: {avg_survivor:.3f}')

if avg_crash > avg_survivor:
    print(f'[hazard_model_smoke] Training sample separation OK')
else:
    print(f'[hazard_model_smoke] FAIL: Training samples not well separated')
    exit(1)
PY
then
    echo -e "[${RED}FAIL${NC}] Hazard scoring test failed"
    exit 1
fi

# Test 6: Verify calibration
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 6: Testing calibration curve..."
if ! python3 - <<'PY' 2>/dev/null
from analysis.survival_model import calibrate_hazard_score

# Test calibration points
test_scores = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
for raw in test_scores:
    calibrated = calibrate_hazard_score(raw)
    print(f'[hazard_model_smoke] raw={raw:.1f} -> calibrated={calibrated:.3f}')

# Verify monotonicity
prev = 0.0
monotonic = True
for raw in test_scores[1:]:
    calibrated = calibrate_hazard_score(raw)
    if calibrated < prev:
        monotonic = False
        break
    prev = calibrated

if monotonic:
    print('[hazard_model_smoke] Calibration monotonicity OK')
else:
    print('[hazard_model_smoke] FAIL: Calibration not monotonic')
    exit(1)
PY
then
    echo -e "[${RED}FAIL${NC}] Calibration test failed"
    exit 1
fi

# Test 7: Validate JSON schema (basic check)
echo -e "[${YELLOW}hazard_model_smoke${NC}] Test 7: Validating JSON schema..."
if ! python3 - <<'PY' 2>/dev/null
import json

with open('strategy/schemas/hazard_score_schema.json') as f:
    schema = json.load(f)

# Check required fields
required_fields = ['hazard_score_raw', 'hazard_score_calibrated', 'is_emergency_exit', 'triggering_features', 'model_version']
for field in required_fields:
    if field not in schema.get('properties', {}):
        print(f'[hazard_model_smoke] FAIL: Missing required field: {field}')
        exit(1)

print('[hazard_model_smoke] JSON schema validation OK')
PY
then
    echo -e "[${RED}FAIL${NC}] JSON schema validation failed"
    exit 1
fi

echo -e "[${GREEN}hazard_model_smoke${NC}] All tests passed!"
echo -e "[${GREEN}OK${NC}] hazard_model_smoke"
