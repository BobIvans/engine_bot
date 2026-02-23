#!/bin/bash
#
# AMM Math Smoke Test
# Validates constant product calculations against fixtures
#
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$PROJECT_ROOT/integration/fixtures/amm"
PYTHON_PATH="$PROJECT_ROOT"

echo "[amm_smoke] Running AMM math smoke tests..."

# Check if fixtures exist
if [ ! -f "$FIXTURES_DIR/scenarios.jsonl" ]; then
    echo "[amm_smoke] ERROR: fixtures not found at $FIXTURES_DIR/scenarios.jsonl" >&2
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${PYTHONPATH:=}"
# Add project root to PYTHONPATH (portable)
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"

PASS_COUNT=0
FAIL_COUNT=0

while IFS= read -r line || [ -n "$line" ]; do
    # strip CR (windows line endings)
    line=${line%$'\r'}
    # Skip empty lines
    [ -z "$line" ] && continue
    
    # Parse JSON
    amount_in=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('amount_in', 0))")
    reserve_in=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('reserve_in', 0))")
    reserve_out=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('reserve_out', 0))")
    fee_bps=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('fee_bps', 30))")
    expected_out=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('expected_out', 0))")
    description=$(echo "$line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('description', ''))")
    
    # Determine case type from description
    if echo "$description" | grep -qi "Tiny"; then
        case_name="Tiny"
    elif echo "$description" | grep -qi "Zero amount"; then
        case_name="ZeroAmount"
    elif echo "$description" | grep -qi "Zero liquidity"; then
        case_name="Zero"
    elif echo "$description" | grep -qi "Huge"; then
        case_name="Huge"
    else
        case_name="Unknown"
    fi
    
    # Run calculation
    if [ "$case_name" = "Zero" ]; then
        # Zero liquidity case should raise ValueError
        if python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.amm_math import get_amount_out
try:
    get_amount_out($amount_in, $reserve_in, $reserve_out, $fee_bps)
    print('ERROR: Expected ValueError but got result')
    sys.exit(1)
except ValueError:
    print('OK')
" 2>/dev/null; then
            echo "[amm_smoke] Case $case_name ($description): OK"
            PASS_COUNT=$((PASS_COUNT+1))
        else
            echo "[amm_smoke] Case $case_name ($description): FAIL - Expected ValueError"
            FAIL_COUNT=$((FAIL_COUNT+1))
        fi
    else
        # Normal case - compare with tolerance
        actual_out=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.amm_math import get_amount_out
print(get_amount_out($amount_in, $reserve_in, $reserve_out, $fee_bps))
" 2>/dev/null)
        
        # Compare with tolerance 1e-6
        if python3 -c "
import sys
actual = $actual_out
expected = $expected_out
tolerance = 1e-6
if abs(actual - expected) <= tolerance:
    print('OK')
else:
    print(f'FAIL: {actual} != {expected}')
    sys.exit(1)
" 2>/dev/null; then
            echo "[amm_smoke] Case $case_name ($description): OK"
            PASS_COUNT=$((PASS_COUNT+1))
        else
            echo "[amm_smoke] Case $case_name ($description): FAIL"
            echo "[amm_smoke]   actual_out=${actual_out} expected_out=${expected_out} fee_bps=${fee_bps} amount_in=${amount_in} reserve_in=${reserve_in} reserve_out=${reserve_out}"
            FAIL_COUNT=$((FAIL_COUNT+1))
        fi
    fi
    
done < "$FIXTURES_DIR/scenarios.jsonl"

echo "[amm_smoke] Results: $PASS_COUNT passed, $FAIL_COUNT failed"

if [ $FAIL_COUNT -eq 0 ]; then
    echo "[amm_smoke] OK"
    exit 0
else
    echo "[amm_smoke] FAIL" >&2
    exit 1
fi
