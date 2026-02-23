#!/usr/bin/env bash
#
# scripts/calibration_smoke.sh
#
# PR-ML.5 Smoke Test for Calibration Loader
# Validates Platt and Isotonic calibration transformations
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "[${YELLOW}calibration_smoke${NC}] Starting calibration smoke test..."

# Test 1: Verify fixtures exist
echo -e "[${YELLOW}calibration_smoke${NC}] Test 1: Checking calibration fixtures..."
PLATT_FILE="$ROOT_DIR/integration/fixtures/ml/calibration_v1_20250201_sample.json"
ISOTONIC_FILE="$ROOT_DIR/integration/fixtures/ml/calibration_v2_20250205_sample.json"

if [[ -f "$PLATT_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] Platt calibration fixture exists"
else
    echo -e "[${RED}FAIL${NC}] Platt fixture not found"
    exit 1
fi

if [[ -f "$ISOTONIC_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] Isotonic calibration fixture exists"
else
    echo -e "[${RED}FAIL${NC}] Isotonic fixture not found"
    exit 1
fi

# Test 2: Verify schema exists
echo -e "[${YELLOW}calibration_smoke${NC}] Test 2: Checking calibration schema..."
SCHEMA_FILE="$ROOT_DIR/strategy/schemas/calibration_schema.json"
if [[ -f "$SCHEMA_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] Calibration schema exists"
else
    echo -e "[${RED}FAIL${NC}] Calibration schema not found"
    exit 1
fi

# Test 3: Test Platt calibration
echo -e "[${YELLOW}calibration_smoke${NC}] Test 3: Testing Platt calibration..."
python3 -c "
import json
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader, clear_calibration_cache

# Clear cache before test
clear_calibration_cache()

# Test Platt calibration - directly load the platt fixture
loader = CalibrationLoader(model_version='v1_20250201', allow_calibration=True, calibration_dir='$ROOT_DIR/integration/fixtures/ml')

test_scores = [0.40, 0.60, 0.80]
calibrated = loader.apply_batch(test_scores)

print(f'[calibration] Platt calibration:')
for raw, cal in zip(test_scores, calibrated):
    print(f'  {raw:.2f} → {cal:.4f}')

# Expected values (using a=-1.85, b=0.32)
# 0.40 → 1/(1+exp(-1.85*0.40+0.32)) = 0.6035
# 0.60 → 1/(1+exp(-1.85*0.60+0.32)) = 0.6878
# 0.80 → 1/(1+exp(-1.85*0.80+0.32)) = 0.7613
expected = [0.6035, 0.6878, 0.7613]
for raw, cal, exp in zip(test_scores, calibrated, expected):
    if abs(cal - exp) < 0.01:
        print(f'[calibration_smoke] {raw:.2f} → {cal:.4f} (expected ~{exp:.4f}): OK')
    else:
        print(f'[calibration_smoke] FAIL: {raw:.2f} → {cal:.4f} (expected ~{exp:.4f})')
        sys.exit(1)

print('[calibration_smoke] Platt calibration validated')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Platt calibration test failed"
    exit 1
}

# Test 4: Test Isotonic calibration
echo -e "[${YELLOW}calibration_smoke${NC}] Test 4: Testing Isotonic calibration..."
python3 -c "
import json
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader, clear_calibration_cache

# Clear cache before test
clear_calibration_cache()

# Test Isotonic calibration - directly load the isotonic fixture
loader = CalibrationLoader(model_version='v2_20250205', allow_calibration=True, calibration_dir='$ROOT_DIR/integration/fixtures/ml')

test_scores = [0.40, 0.90]
calibrated = loader.apply_batch(test_scores)

print(f'[calibration] Isotonic calibration:')
for raw, cal in zip(test_scores, calibrated):
    print(f'  {raw:.2f} → {cal:.4f}')

# Expected values (interpolation in [0.0,0.25,0.45,0.62,0.85])
# 0.40: between 0.3→0.25 and 0.5→0.45
# 0.90: between 0.7→0.62 and 1.0→0.85
expected_0_40 = 0.25 + (0.40-0.30)/(0.50-0.30) * (0.45-0.25)  # = 0.35
expected_0_90 = 0.62 + (0.90-0.70)/(1.00-0.70) * (0.85-0.62)  # = 0.78

if abs(calibrated[0] - expected_0_40) < 0.01:
    print(f'[calibration_smoke] 0.40 → {calibrated[0]:.4f} (expected ~{expected_0_40:.2f}): OK')
else:
    print(f'[calibration_smoke] FAIL: 0.40 → {calibrated[0]:.4f} (expected ~{expected_0_40:.2f})')
    sys.exit(1)

if abs(calibrated[1] - expected_0_90) < 0.01:
    print(f'[calibration_smoke] 0.90 → {calibrated[1]:.4f} (expected ~{expected_0_90:.2f}): OK')
else:
    print(f'[calibration_smoke] FAIL: 0.90 → {calibrated[1]:.4f} (expected ~{expected_0_90:.2f})')
    sys.exit(1)

print('[calibration_smoke] Isotonic calibration validated')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Isotonic calibration test failed"
    exit 1
}

# Test 5: Test monotonicity
echo -e "[${YELLOW}calibration_smoke${NC}] Test 5: Testing monotonicity..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader

loader = CalibrationLoader(model_version='v1_20250201', allow_calibration=True)

# Test monotonicity
test_scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
calibrated = loader.apply_batch(test_scores)

monotonic = True
for i in range(len(calibrated) - 1):
    if calibrated[i] > calibrated[i + 1]:
        monotonic = False
        break

if monotonic:
    print('[calibration_smoke] Monotonicity: OK')
else:
    print('[calibration_smoke] FAIL: Monotonicity violated')
    for i, (raw, cal) in enumerate(zip(test_scores, calibrated)):
        print(f'  {raw:.1f} → {cal:.4f}')
    sys.exit(1)
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Monotonicity test failed"
    exit 1
}

# Test 6: Test range clamping
echo -e "[${YELLOW}calibration_smoke${NC}] Test 6: Testing range clamping..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader

loader = CalibrationLoader(model_version='v1_20250201', allow_calibration=True)

# Test edge cases
edge_cases = [0.0, 1.0]
calibrated = loader.apply_batch(edge_cases)

for raw, cal in zip(edge_cases, calibrated):
    if 0.0 <= cal <= 1.0:
        print(f'[calibration_smoke] {raw:.1f} → {cal:.4f} (in range): OK')
    else:
        print(f'[calibration_smoke] FAIL: {raw:.1f} → {cal:.4f} (out of range)')
        sys.exit(1)
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Range clamping test failed"
    exit 1
}

# Test 7: Test identity fallback
echo -e "[${YELLOW}calibration_smoke${NC}] Test 7: Testing identity fallback..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader

# Test with disabled calibration
loader = CalibrationLoader(model_version='v1_20250201', allow_calibration=False)

raw = 0.60
cal = loader.apply(raw)

if cal == raw:
    print(f'[calibration_smoke] Identity fallback: {raw:.2f} → {cal:.2f}: OK')
else:
    print(f'[calibration_smoke] FAIL: Identity fallback not working')
    sys.exit(1)
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Identity fallback test failed"
    exit 1
}

# Test 8: Test metrics retrieval
echo -e "[${YELLOW}calibration_smoke${NC}] Test 8: Testing metrics retrieval..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from integration.models.calibration_loader import CalibrationLoader

loader = CalibrationLoader(model_version='v1_20250201', allow_calibration=True)
metrics = loader.get_metrics()

if metrics:
    print(f'[calibration_smoke] Metrics retrieved: Brier={metrics.get(\"brier_score\", \"N/A\")}, ECE={metrics.get(\"ece\", \"N/A\")}: OK')
else:
    print(f'[calibration_smoke] FAIL: No metrics retrieved')
    sys.exit(1)
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Metrics retrieval test failed"
    exit 1
}

echo -e "[${GREEN}calibration_smoke${NC}] All tests passed!"
echo -e "[${GREEN}OK${NC}] calibration_smoke"
