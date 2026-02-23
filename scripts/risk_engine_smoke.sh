#!/bin/bash
# Risk Engine Smoke Test
# Tests two scenarios:
# 1. Max Open Positions Test - verifies RISK_MAX_POSITIONS rejection
# 2. Kill-Switch Test - verifies RISK_KILL_SWITCH rejection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_test() {
    local test_name="$1"
    local expected_reason="$2"
    local trade="$3"
    local portfolio="$4"
    local cfg="$5"
    local python_code="$6"

    echo "[risk_engine_smoke] Running: $test_name" >&2

    result=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/..')
from integration.portfolio_stub import PortfolioStub
from strategy.risk_engine import apply_risk_limits
$python_code
" 2>&1)

    if echo "$result" | grep -q "Error:"; then
        echo "[risk_engine_smoke] FAIL: $test_name" >&2
        echo "[risk_engine_smoke] Error: $result" >&2
        exit 1
    fi

    if echo "$result" | grep -q "$expected_reason"; then
        echo "[risk_engine_smoke] PASS: $test_name" >&2
    else
        echo "[risk_engine_smoke] FAIL: $test_name" >&2
        echo "[risk_engine_smoke] Expected rejection: $expected_reason" >&2
        echo "[risk_engine_smoke] Got: $result" >&2
        exit 1
    fi
}

echo "[risk_engine_smoke] Starting risk engine smoke tests..." >&2

# Test 1: Max Open Positions Test
# Config: max_open_positions: 1
# Portfolio: open_positions: 1
# Expected: risk_max_positions rejection
run_test "Max Open Positions Test" "risk_max_positions" \
    "trade = {'symbol': 'BTC'}" \
    "portfolio = PortfolioStub(equity_usd=1000, peak_equity_usd=1000, open_positions=1, day_pnl_usd=0, consecutive_losses=0, cooldown_until=0.0, active_counts_by_tier={})" \
    "cfg = {'risk': {'limits': {'max_open_positions': 1}}}" \
    "
trade = {'symbol': 'BTC'}
portfolio = PortfolioStub(equity_usd=1000, peak_equity_usd=1000, open_positions=1, day_pnl_usd=0, consecutive_losses=0, cooldown_until=0.0, active_counts_by_tier={})
cfg = {'risk': {'limits': {'max_open_positions': 1}}}
allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
if not allowed:
    print(reason)
else:
    print('Error: Trade was allowed but should have been rejected')
    exit(1)
"

# Test 2: Kill-Switch Test
# Config: max_daily_loss_pct: 0.05 (5%), bankroll: 1000 (limit $50)
# Portfolio: day_pnl_usd: -51
# Expected: risk_kill_switch rejection
run_test "Kill-Switch Test" "risk_kill_switch" \
    "trade = {'symbol': 'BTC'}" \
    "portfolio = PortfolioStub(equity_usd=949, peak_equity_usd=1000, open_positions=0, day_pnl_usd=-51, consecutive_losses=0, cooldown_until=0.0, active_counts_by_tier={})" \
    "cfg = {'risk': {'limits': {'max_daily_loss_pct': 0.05}}}" \
    "
trade = {'symbol': 'BTC'}
portfolio = PortfolioStub(equity_usd=949, peak_equity_usd=1000, open_positions=0, day_pnl_usd=-51, consecutive_losses=0, cooldown_until=0.0, active_counts_by_tier={})
cfg = {'risk': {'limits': {'max_daily_loss_pct': 0.05}}}
allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
if not allowed:
    print(reason)
else:
    print('Error: Trade was rejected but should have passed')
    exit(1)
"

echo "[risk_engine_smoke] OK ✅" >&2
