#!/bin/bash
# Risk Cooldown Smoke Test
# Tests two scenarios:
# 1. Cooldown Active (Reject) - verifies RISK_COOLDOWN rejection when trade.ts < cooldown_until
# 2. Cooldown Expired (Pass) - verifies trade passes when cooldown has expired

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_test() {
    local test_name="$1"
    local expected_result="$2"
    local python_code="$3"

    echo "[risk_cooldown_smoke] Running: $test_name" >&2

    result=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/..')
from integration.portfolio_stub import PortfolioStub
from integration.trade_types import Trade
from strategy.risk_engine import apply_risk_limits
$python_code
" 2>&1)

    if echo "$result" | grep -q "Error:"; then
        echo "[risk_cooldown_smoke] FAIL: $test_name" >&2
        echo "[risk_cooldown_smoke] Error: $result" >&2
        exit 1
    fi

    if echo "$result" | grep -q "$expected_result"; then
        echo "[risk_cooldown_smoke] PASS: $test_name" >&2
    else
        echo "[risk_cooldown_smoke] FAIL: $test_name" >&2
        echo "[risk_cooldown_smoke] Expected: $expected_result" >&2
        echo "[risk_cooldown_smoke] Got: $result" >&2
        exit 1
    fi
}

echo "[risk_cooldown_smoke] Starting risk cooldown smoke tests..." >&2

# Test 1: Cooldown Active (Reject)
# Portfolio: cooldown_until set to future timestamp (current_time + 3600)
# Config: risk.limits.cooldown.enabled = True
# Expected: (False, RISK_COOLDOWN)
run_test "Cooldown Active (Reject)" "risk_cooldown" "
current_time = 1707000000  # Fixed timestamp for reproducibility
future_time = current_time + 3600

trade = Trade(ts=str(current_time), wallet='test', mint='test', side='buy')
portfolio = PortfolioStub(equity_usd=1000, peak_equity_usd=1000, cooldown_until=future_time)
cfg = {'risk': {'limits': {'cooldown': {'enabled': True}}}}
allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
if not allowed:
    print(reason)
else:
    print('Error: Trade was allowed but should have been rejected')
    exit(1)
"

# Test 2: Cooldown Expired (Pass)
# Portfolio: cooldown_until set to past timestamp (current_time - 3600)
# Config: risk.limits.cooldown.enabled = True
# Expected: (True, None) - passes to next checks
run_test "Cooldown Expired (Pass)" "True" "
current_time = 1707000000  # Fixed timestamp for reproducibility
past_time = current_time - 3600

trade = Trade(ts=str(current_time), wallet='test', mint='test', side='buy')
portfolio = PortfolioStub(equity_usd=1000, peak_equity_usd=1000, cooldown_until=past_time)
cfg = {'risk': {'limits': {'cooldown': {'enabled': True}}}}
allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
if allowed:
    print('True')
else:
    print('Error: Trade was rejected but should have passed')
    exit(1)
"

echo "[risk_cooldown_smoke] OK ✅" >&2
