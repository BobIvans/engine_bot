#!/bin/bash
#
# Slippage Smoke Test
# Validates slippage calculation math against test scenarios
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIOS_FILE="$PROJECT_ROOT/integration/fixtures/slippage/scenarios.jsonl"
PYTHON_PATH="$PROJECT_ROOT"

echo "[slippage_smoke] Running slippage calculation smoke tests..."

# Check if scenarios file exists
if [ ! -f "$SCENARIOS_FILE" ]; then
    echo "[slippage_smoke] ERROR: scenarios file not found at $SCENARIOS_FILE" >&2
    exit 1
fi

# Add project root to PYTHONPATH
export PYTHONPATH="$PYTHON_PATH:$PYTHONPATH"

# Run slippage math tests
python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
import json
from strategy.execution_math import calculate_linear_impact_bps, MAX_SLIPPAGE_BPS

passed = 0
failed = 0

with open('$SCENARIOS_FILE', 'r') as f:
    for line in f:
        if line.strip():
            scenario = json.loads(line)
            scenario_id = scenario['id']
            size_usd = scenario['size_usd']
            liquidity_usd = scenario['liquidity_usd']
            scalar = scenario['scalar']
            expected = scenario['expected_slippage']

            actual = calculate_linear_impact_bps(size_usd, liquidity_usd, scalar)

            # Check if within tolerance (accounting for floating point)
            tolerance = 0.01  # 0.01 bps tolerance
            if abs(actual - expected) <= tolerance:
                print(f'[slippage_smoke] Scenario {scenario_id}... PASS ({actual:.3f} bps)')
                passed += 1
            else:
                print(f'[slippage_smoke] Scenario {scenario_id}... FAIL', file=sys.stderr)
                print(f'  Expected: {expected} bps, Got: {actual:.3f} bps', file=sys.stderr)
                failed += 1

# Test edge cases
print('[slippage_smoke] Testing edge cases...')

# Test zero size
zero_size = calculate_linear_impact_bps(0, 1000000, 0.5)
if zero_size == 0.0:
    print('[slippage_smoke] Edge case zero_size... PASS')
    passed += 1
else:
    print(f'[slippage_smoke] Edge case zero_size... FAIL (got {zero_size})', file=sys.stderr)
    failed += 1

# Test NaN handling
nan_result = calculate_linear_impact_bps(float('nan'), 1000000, 0.5)
if nan_result == MAX_SLIPPAGE_BPS:
    print('[slippage_smoke] Edge case NaN handling... PASS')
    passed += 1
else:
    print(f'[slippage_smoke] Edge case NaN handling... FAIL (got {nan_result})', file=sys.stderr)
    failed += 1

print(f'[slippage_smoke] Results: {passed} passed, {failed} failed')

if failed > 0:
    print('[slippage_smoke] FAIL', file=sys.stderr)
    sys.exit(1)

print('[slippage_smoke] OK')
"
