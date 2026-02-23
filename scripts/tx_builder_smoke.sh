#!/bin/bash
# scripts/tx_builder_smoke.sh
# Smoke test for Transaction Builder (Partial Exits & SL Updates)

set -e

GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[tx_builder_smoke] Running transaction builder smoke test..." >&2

# Run Python smoke test
cd "$ROOT_DIR"
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')

from execution.transaction_builder import calculate_swap_amount, build_swap_instruction
from strategy.trade_types import ExitSignal, ExitType, SimulatedTrade
from execution.sim_fill import process_exit_signal

# Test 1: Integer precision - 50% of 1001 tokens
balance = 1001
amount = calculate_swap_amount(balance, 0.5)
assert amount == 500, f'Test 1 failed: 50% of 1001 = {amount} (expected 500)'
print('Test 1 PASSED: 50% of 1001 = 500 (no float drift)', file=sys.stderr)

# Test 2: Integer precision - 33% of 1000 tokens
balance = 1000
amount = calculate_swap_amount(balance, 0.33)
assert amount == 330, f'Test 2 failed: 33% of 1000 = {amount} (expected 330)'
print('Test 2 PASSED: 33% of 1000 = 330 (rounding correct)', file=sys.stderr)

# Test 3: Edge case - 1% of 100 tokens
balance = 100
amount = calculate_swap_amount(balance, 0.01)
assert amount == 1, f'Test 3 failed: 1% of 100 = {amount} (expected 1, min 1)'
print('Test 3 PASSED: 1% of 100 = 1 (min enforced)', file=sys.stderr)

# Test 4: Create a simulated trade
trade = SimulatedTrade(
    wallet='WalletA',
    mint='SOL123',
    entry_price=100.0,
    size_remaining=1000.0,  # 1000 tokens
    size_initial=1000.0,
    realized_pnl=0.0,
    status='OPEN',
)
assert trade.status == 'OPEN', 'Trade should start as OPEN'
print('Test 4 PASSED: Trade initialized with OPEN status', file=sys.stderr)

# Test 5: Partial exit - 50%
signal = ExitSignal(exit_type=ExitType.PARTIAL, size_pct=0.5)
result = process_exit_signal(trade, signal, current_price=150.0)
assert result.trade.status == 'OPEN', f'Partial exit should keep trade OPEN, got {result.trade.status}'
assert result.trade.size_remaining == 500.0, f'Expected 500 remaining, got {result.trade.size_remaining}'
assert result.amount_sold == 500, f'Expected 500 sold, got {result.amount_sold}'
assert result.is_closed == False, 'Partial exit should not close trade'
print('Test 5 PASSED: 50% partial exit -> OPEN, 500 remaining', file=sys.stderr)

# Test 6: Full exit of remaining (use MARKET_CLOSE for full exit)
signal_full = ExitSignal(exit_type=ExitType.MARKET_CLOSE, size_pct=1.0)
result_full = process_exit_signal(result.trade, signal_full, current_price=150.0)
assert result_full.trade.status == 'CLOSED', f'Full exit should close trade, got {result_full.trade.status}'
assert result_full.trade.size_remaining == 0.0, f'Expected 0 remaining, got {result_full.trade.size_remaining}'
assert result_full.is_closed == True, 'Full exit should be closed'
print('Test 6 PASSED: Full exit -> CLOSED, 0 remaining', file=sys.stderr)

# Test 7: Update trailing stop
trade2 = SimulatedTrade(
    wallet='WalletB',
    mint='SOL456',
    entry_price=100.0,
    size_remaining=1000.0,
    size_initial=1000.0,
    realized_pnl=0.0,
    status='OPEN',
)
signal_trail = ExitSignal(
    exit_type=ExitType.TRAILING_STOP_UPDATE,
    size_pct=0.0,
    trail_stop_pct=0.05,
    trail_activation_pct=0.03,
)
result_trail = process_exit_signal(trade2, signal_trail, current_price=120.0)
assert result_trail.trade.trail_stop_price == 114.0, f'Expected trail stop at 114.0, got {result_trail.trade.trail_stop_price}'
assert result_trail.trade.trail_activation_price == 123.6, f'Expected activation at 123.6, got {result_trail.trade.trail_activation_price}'
assert result_trail.trade.status == 'OPEN', 'SL update should not change status'
print('Test 7 PASSED: Trailing stop updated (stop=114.0, activation=123.6)', file=sys.stderr)

print('', file=sys.stderr)
print('[tx_builder_smoke] All tests passed!', file=sys.stderr)
"

echo -e "${GREEN}[tx_builder_smoke] OK ✅${NC}"
