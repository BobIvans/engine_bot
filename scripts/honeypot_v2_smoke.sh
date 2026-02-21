#!/bin/bash
#
# Honeypot Filter v2 Smoke Test
# Validates token security evaluation logic against fixtures
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$PROJECT_ROOT/integration/fixtures/honeypot_v2"
PYTHON_PATH="$PROJECT_ROOT"

echo "[honeypot_v2_smoke] Running honeypot v2 smoke tests..."

# Check if fixtures exist
if [ ! -f "$FIXTURES_DIR/token_snapshot.csv" ]; then
    echo "[honeypot_v2_smoke] ERROR: fixtures not found at $FIXTURES_DIR/token_snapshot.csv" >&2
    exit 1
fi

# Add project root to PYTHONPATH
export PYTHONPATH="$PYTHON_PATH:$PYTHONPATH"

PASS_COUNT=0
FAIL_COUNT=0

# Read CSV and process each row
while IFS=',' read -r symbol buy_tax sell_tax is_freezable mint_authority sim_ok expected_result; do
    # Skip header row
    [ "$symbol" = "symbol" ] && continue
    
    # Skip empty lines
    [ -z "$symbol" ] && continue
    
    # Parse boolean fields
    if [ "$is_freezable" = "true" ] || [ "$is_freezable" = "TRUE" ]; then
        is_freezable_bool="True"
    else
        is_freezable_bool="False"
    fi
    
    if [ "$mint_authority" = "true" ] || [ "$mint_authority" = "TRUE" ]; then
        mint_authority_bool="True"
    else
        mint_authority_bool="False"
    fi
    
    if [ "$sim_ok" = "true" ] || [ "$sim_ok" = "TRUE" ]; then
        sim_ok_bool="True"
    else
        sim_ok_bool="False"
    fi
    
    # Parse tax values (handle empty strings)
    if [ -z "$buy_tax" ]; then
        buy_tax_value="None"
        buy_tax_py="None"
    else
        buy_tax_value="$buy_tax"
        buy_tax_py="$buy_tax"
    fi
    
    if [ -z "$sell_tax" ]; then
        sell_tax_value="None"
        sell_tax_py="None"
    else
        sell_tax_value="$sell_tax"
        sell_tax_py="$sell_tax"
    fi
    
    # Build data dict for Python
    data_dict="{'symbol': '$symbol', 'buy_tax': $buy_tax_py, 'sell_tax': $sell_tax_py, 'is_freezable': $is_freezable_bool, 'mint_authority': $mint_authority_bool, 'sim_ok': $sim_ok_bool}"
    
    # Build params dict - use allow_unknown for SOL_UNKNOWN_ALLOWED
    if [ "$symbol" = "SOL_UNKNOWN_ALLOWED" ]; then
        params_dict="{'max_tax_bps': 1000, 'block_freeze_authority': True, 'allow_unknown': True}"
    else
        params_dict="{'max_tax_bps': 1000, 'block_freeze_authority': True, 'allow_unknown': False}"
    fi
    
    # Run evaluation
    result=$(python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from strategy.honeypot_filter import evaluate_security_dict

data = $data_dict
params = $params_dict

passed, reasons = evaluate_security_dict(data, params)
result = 'PASS' if passed else 'REJECT'
print(result + (':' + ','.join(reasons) if reasons else ''))
" 2>&1) || {
    echo "[honeypot_v2_smoke] Testing $symbol... ERROR: $result" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
}
    
    # Parse result
    actual_result=$(echo "$result" | cut -d':' -f1)
    reasons_output=$(echo "$result" | cut -d':' -f2-)
    
    # Compare with expected
    if [ "$actual_result" = "$expected_result" ]; then
        if [ "$actual_result" = "PASS" ]; then
            echo "[honeypot_v2_smoke] Testing $symbol... PASS"
        else
            echo "[honeypot_v2_smoke] Testing $symbol... PASS (Rejected as expected)"
        fi
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "[honeypot_v2_smoke] Testing $symbol... FAIL - Expected $expected_result, got $actual_result" >&2
        if [ -n "$reasons_output" ]; then
            echo "[honeypot_v2_smoke]   Reasons: $reasons_output" >&2
        fi
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    
done < "$FIXTURES_DIR/token_snapshot.csv"

echo "[honeypot_v2_smoke] Results: $PASS_COUNT passed, $FAIL_COUNT failed"

if [ $FAIL_COUNT -eq 0 ]; then
    echo "[honeypot_v2_smoke] OK"
    exit 0
else
    echo "[honeypot_v2_smoke] FAIL" >&2
    exit 1
fi
