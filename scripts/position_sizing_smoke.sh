#!/usr/bin/env bash
#
# scripts/position_sizing_smoke.sh
#
# PR-RM.1 Smoke Test for Polymarket-Aware Position Sizing
# Validates adaptive position sizing based on risk regime
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "[${YELLOW}position_sizing_smoke${NC}] Starting position sizing smoke test..."

# Test 1: Verify fixture exists
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 1: Checking fixture..."
FIXTURE_FILE="$ROOT_DIR/integration/fixtures/risk/position_sizing_sample.json"
if [[ -f "$FIXTURE_FILE" ]]; then
    echo -e "[${GREEN}OK${NC}] position_sizing_sample.json exists"
else
    echo -e "[${RED}FAIL${NC}] position_sizing_sample.json not found"
    exit 1
fi

# Test 2: Verify schema extension exists
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 2: Checking feature vector schema..."
SCHEMA_FILE="$ROOT_DIR/strategy/schemas/feature_vector_schema.json"
if [[ -f "$SCHEMA_FILE" ]]; then
    if grep -q "position_pct_adjusted" "$SCHEMA_FILE"; then
        echo -e "[${GREEN}OK${NC}] feature_vector_schema.json has position fields"
    else
        echo -e "[${RED}FAIL${NC}] feature_vector_schema.json missing position fields"
        exit 1
    fi
else
    echo -e "[${RED}FAIL${NC}] feature_vector_schema.json not found"
    exit 1
fi

# Test 3: Test compute_risk_aware_position_pct function from logic.py
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 3: Testing position sizing logic..."
python3 -c "
import json
import sys
sys.path.insert(0, '$ROOT_DIR')
from strategy.logic import compute_risk_aware_position_pct

# Load fixture
with open('integration/fixtures/risk/position_sizing_sample.json') as f:
    data = json.load(f)

base_pct = data['base_position_pct']
risk_beta = data['risk_beta']
max_pct = data['max_position_pct_risk_on']
min_pct = data['min_position_pct_risk_off']

# Test scenarios
for scenario in data['scenarios']:
    risk_regime = scenario['risk_regime']
    expected = scenario['expected_position_pct']
    
    adjusted, method = compute_risk_aware_position_pct(
        base_pct=base_pct,
        risk_regime=risk_regime,
        risk_beta=risk_beta,
        min_pct=min_pct,
        max_pct=max_pct
    )
    
    # Verify calculation
    if abs(adjusted - expected) < 0.001:
        print(f'[position_sizing_smoke] risk_regime={risk_regime:+.2f} → position {adjusted:.4f} ({adjusted*100:.2f}%): OK')
    else:
        print(f'[position_sizing_smoke] FAIL: risk_regime={risk_regime} expected {expected} got {adjusted}')
        sys.exit(1)
    
    # Verify method
    if method == scenario['expected_method']:
        print(f'[position_sizing_smoke] method={method}: OK')
    else:
        print(f'[position_sizing_smoke] FAIL: method {method} != {scenario[\"expected_method\"]}')
        sys.exit(1)

print('[position_sizing_smoke] All scenarios validated')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Position sizing logic test failed"
    exit 1
}

# Test 4: Test safety caps
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 4: Testing safety caps..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from strategy.logic import compute_risk_aware_position_pct

# Test min cap (risk_regime = -1.0)
adjusted, _ = compute_risk_aware_position_pct(0.02, -1.0, 0.5, 0.01, 0.05)
if abs(adjusted - 0.01) < 0.001:
    print(f'[position_sizing_smoke] Min cap test (risk_regime=-1.0): {adjusted:.4f}: OK')
else:
    print(f'[position_sizing_smoke] FAIL: Min cap {adjusted} != 0.01')
    sys.exit(1)

# Test max cap (risk_regime = +1.0)
adjusted, _ = compute_risk_aware_position_pct(0.02, 1.0, 0.5, 0.01, 0.05)
if abs(adjusted - 0.03) < 0.001:
    print(f'[position_sizing_smoke] Max cap test (risk_regime=+1.0): {adjusted:.4f}: OK')
else:
    print(f'[position_sizing_smoke] FAIL: Max cap {adjusted} != 0.03')
    sys.exit(1)

# Test fixed mode (disabled)
adjusted, method = compute_risk_aware_position_pct(0.02, 0.85, 0.5, 0.01, 0.05, allow_risk_aware=False)
if adjusted == 0.02 and method == 'fixed':
    print(f'[position_sizing_smoke] Fixed mode test: {adjusted:.4f}: OK')
else:
    print(f'[position_sizing_smoke] FAIL: Fixed mode {adjusted}/{method}')
    sys.exit(1)

print('[position_sizing_smoke] Safety caps validated')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Safety caps test failed"
    exit 1
}

# Test 5: Verify schema has required fields
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 5: Validating schema fields..."
python3 -c "
import json

with open('strategy/schemas/feature_vector_schema.json') as f:
    schema = json.load(f)

required_fields = [
    'position_pct_raw',
    'position_pct_adjusted',
    'risk_regime_used',
    'position_sizing_method'
]

props = schema.get('properties', {})
for field in required_fields:
    if field in props:
        print(f'[position_sizing_smoke] Field \"{field}\" exists: OK')
    else:
        print(f'[position_sizing_smoke] FAIL: Missing field \"{field}\"')
        exit(1)

print('[position_sizing_smoke] Schema validation passed')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Schema validation failed"
    exit 1
}

# Test 6: Calculate expected metrics
echo -e "[${YELLOW}position_sizing_smoke${NC}] Test 6: Calculating expected metrics..."
python3 -c "
import json

with open('integration/fixtures/risk/position_sizing_sample.json') as f:
    data = json.load(f)

position_pcts = []
regime_distribution = {'risk_on': 0, 'neutral': 0, 'risk_off': 0}

for scenario in data['scenarios']:
    risk_regime = scenario['risk_regime']
    if risk_regime > 0:
        regime_distribution['risk_on'] += 1
    elif risk_regime < 0:
        regime_distribution['risk_off'] += 1
    else:
        regime_distribution['neutral'] += 1
    
    # Recalculate
    base_pct = data['base_position_pct']
    risk_beta = data['risk_beta']
    max_pct = data['max_position_pct_risk_on']
    min_pct = data['min_position_pct_risk_off']
    
    adjusted = base_pct * (1.0 + risk_beta * risk_regime)
    adjusted = max(min_pct, min(max_pct, adjusted))
    adjusted = max(0.01, min(0.05, adjusted))
    position_pcts.append(adjusted)

avg_pct = sum(position_pcts) / len(position_pcts)
print(f'[position_sizing_smoke] Expected avg_position_pct: {avg_pct:.4f}')
print(f'[position_sizing_smoke] Expected regime_distribution: {regime_distribution}')

# Verify specific values
for scenario in data['scenarios']:
    risk_regime = scenario['risk_regime']
    expected = scenario['expected_position_pct']
    print(f'[position_sizing_smoke] risk_regime={risk_regime:+.2f} → expected_position_pct={expected:.4f}')
" 2>/dev/null || {
    echo -e "[${RED}FAIL${NC}] Metrics calculation failed"
    exit 1
}

echo -e "[${GREEN}position_sizing_smoke${NC}] All tests passed!"
echo -e "[${GREEN}OK${NC}] position_sizing_smoke"
