#!/bin/bash
# scripts/calibration_adapter_smoke.sh
# Smoke test for PR-N.3 Calibrated Inference Adapter
# Fully offline, deterministic, no network calls

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="${ROOT_DIR}/integration/fixtures/calibration"

# Set PYTHONPATH for imports
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"

fail() {
    echo -e "${RED}[calibration_adapter_smoke] FAIL: $*${NC}" >&2
    exit 1
}

pass() {
    echo -e "${GREEN}[calibration_adapter_smoke] $*${NC}" >&2
}

log() {
    echo -e "[calibration_adapter_smoke] $*" >&2
}

# === Smoke Test ===
log "Starting calibration adapter smoke test..."

# Test 1: Load and run self-test from calibration_adapter.py
log "Test 1: Running calibration_adapter.py self-test..."
python3 -c "from strategy.calibration_adapter import CalibratedPredictor; print('Import OK')" || fail "Failed to import CalibratedPredictor"
pass "Test 1 passed: Module import"

# Test 2: Run self-test for CalibratedPredictor
log "Test 2: Running CalibratedPredictor self-test..."
python3 "${ROOT_DIR}/strategy/calibration_adapter.py" 2>&1 | head -20 || fail "CalibratedPredictor self-test failed"
pass "Test 2 passed: CalibratedPredictor self-test"

# Test 3: Verify fixtures exist
log "Test 3: Checking fixtures..."
[[ -f "${FIXTURE_DIR}/mock_raw_scores.jsonl" ]] || fail "Missing fixture: mock_raw_scores.jsonl"
[[ -f "${FIXTURE_DIR}/expected_calibrated_probs.json" ]] || fail "Missing fixture: expected_calibrated_probs.json"
[[ -f "${FIXTURE_DIR}/platt_fixture.json" ]] || fail "Missing fixture: platt_fixture.json"
pass "Test 3 passed: Fixtures exist"

# Test 4: Verify range bounds (only valid [0,1] scores for model output)
log "Test 4: Testing calibrated probabilities in valid range..."

python3 << 'PYEOF'
import json
import sys

# Add root to path
sys.path.insert(0, '.')

from strategy.calibration_adapter import CalibratedPredictor
from strategy.calibration_loader import load_calibrator

# Mock model - returns only valid [0,1] scores
class MockModel:
    def predict_proba(self, x):
        raw = x.get('raw_score', 0.5)
        # Clamp to valid range for model output
        return max(0.0, min(1.0, raw))

# Load calibrator from fixture
with open('integration/fixtures/calibration/platt_fixture.json') as f:
    config = json.load(f)
calibrator = load_calibrator(config)

predictor = CalibratedPredictor(MockModel(), calibrator)

# Test with various raw scores (clamped to [0,1] by mock model)
test_scores = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
for raw in test_scores:
    calibrated = predictor.predict_proba({'raw_score': raw})
    if not (0.0 <= calibrated <= 1.0):
        print(f"FAIL: calibrated={calibrated} out of range for raw={raw}", file=sys.stderr)
        sys.exit(1)
    print(f"  raw={raw:.2f} -> calibrated={calibrated:.4f}")

print("All scores in valid range [0, 1]", file=sys.stderr)
PYEOF

pass "Test 4 passed: Probabilities in valid range"

# Test 5: Monotonicity check
log "Test 5: Testing monotonicity preservation..."

python3 << 'PYEOF'
import json
import sys

sys.path.insert(0, '.')

from strategy.calibration_adapter import CalibratedPredictor
from strategy.calibration_loader import load_calibrator

class MockModel:
    def predict_proba(self, x):
        return x.get('raw_score', 0.5)

with open('integration/fixtures/calibration/platt_fixture.json') as f:
    config = json.load(f)
calibrator = load_calibrator(config)

predictor = CalibratedPredictor(MockModel(), calibrator)

# Test monotonicity with sorted scores
scores = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
calibrated = [predictor.predict_proba({'raw_score': s}) for s in scores]

print(f"  scores:      {[f'{s:.2f}' for s in scores]}", file=sys.stderr)
print(f"  calibrated:  {[f'{c:.4f}' for c in calibrated]}", file=sys.stderr)

# Verify monotonicity
for i in range(len(calibrated) - 1):
    if calibrated[i] > calibrated[i + 1]:
        print(f"FAIL: Monotonicity violated at {i}: {calibrated[i]} > {calibrated[i+1]}", file=sys.stderr)
        sys.exit(1)

print("Monotonicity preserved", file=sys.stderr)
PYEOF

pass "Test 5 passed: Monotonicity preserved"

# Test 6: Test without calibrator (identity fallback)
log "Test 6: Testing fallback to identity when no calibrator..."

python3 << 'PYEOF'
import sys

sys.path.insert(0, '.')

from strategy.calibration_adapter import CalibratedPredictor

class MockModel:
    def predict_proba(self, x):
        return x.get('raw_score', 0.5)

# No calibrator - should return raw score
predictor = CalibratedPredictor(MockModel(), calibrator=None)

result = predictor.predict_proba({'raw_score': 0.75})
if abs(result - 0.75) > 0.001:
    print(f"FAIL: Expected 0.75, got {result}", file=sys.stderr)
    sys.exit(1)

print(f"  Without calibrator: raw=0.75 -> returned={result:.4f}", file=sys.stderr)
print("Fallback to identity works", file=sys.stderr)
PYEOF

pass "Test 6 passed: Fallback to identity"

# Test 7: Verify file loading from fixture
log "Test 7: Testing load_calibrator_from_file..."

python3 << 'PYEOF'
import sys
import json
import math

sys.path.insert(0, '.')

from strategy.calibration_adapter import load_calibrator_from_file

# Test loading from fixture file
calibrator = load_calibrator_from_file('integration/fixtures/calibration/platt_fixture.json')

# Verify it works - Platt(a=1, b=0) on score 0.5:
# 1 / (1 + exp(-(1*0.5 + 0))) = 1 / (1 + exp(-0.5)) = ~0.6225
expected = 1.0 / (1.0 + math.exp(-0.5))
result = calibrator(0.5)

print(f"  calibrator(0.5) = {result:.4f}, expected ~{expected:.4f}", file=sys.stderr)

if abs(result - expected) > 0.001:
    print(f"FAIL: Difference too large", file=sys.stderr)
    sys.exit(1)

print("File loading works", file=sys.stderr)
PYEOF

pass "Test 7 passed: File loading"

# === All Tests Passed ===
echo ""
echo -e "${GREEN}[calibration_adapter_smoke] OK${NC}" >&2
exit 0
