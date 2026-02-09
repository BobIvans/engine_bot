#!/bin/bash
set -e

# PR-L.2 Chain Reaction Logic Smoke Test
# Tests: 
# 1. Score 0.0 -> HOLD
# 2. Score 0.6 (>= 0.5) -> CLOSE_FULL (immediate_exit)
# 3. Disabled config -> HOLD (even with Score 1.0)
# 4. tighten_sl action triggers when PnL <= panic_sl_pct

cd "$(dirname "$0")/.."

echo "[overlay_lint] running chain reaction smoke..." >&2

python3 -c "
import sys
sys.path.insert(0, '.')

from strategy.exits import PositionState, ExitAction

# Test configs
cfg_enabled_immediate = {
    'modes': {
        'A': {
            'exits': {
                'chain_reaction': {
                    'enabled': True,
                    'threshold': 0.5,
                    'action': 'immediate_exit'
                }
            }
        }
    }
}

cfg_disabled = {
    'modes': {
        'C': {
            'exits': {}  # No chain_reaction section
        }
    }
}

cfg_tighten_sl = {
    'modes': {
        'A': {
            'exits': {
                'chain_reaction': {
                    'enabled': True,
                    'threshold': 0.5,
                    'action': 'tighten_sl',
                    'panic_sl_pct': -0.02
                }
            }
        }
    }
}

from strategy.exits import evaluate_exit

# Test 1: Score 0.0 -> HOLD
state1 = PositionState(
    entry_price=100.0,
    current_price=102.0,
    peak_price=102.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=0.0
)
result1 = evaluate_exit(state1, cfg_enabled_immediate)
assert result1.action == ExitAction.HOLD, f'Test 1 failed: expected HOLD, got {result1.action}'
print('Test 1: Score 0.0 -> HOLD ... OK', file=sys.stderr)

# Test 2: Score 0.6 (>= 0.5) -> CLOSE_FULL (immediate_exit)
state2 = PositionState(
    entry_price=100.0,
    current_price=102.0,
    peak_price=102.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=0.6
)
result2 = evaluate_exit(state2, cfg_enabled_immediate)
assert result2.action == ExitAction.CLOSE_FULL, f'Test 2 failed: expected CLOSE_FULL, got {result2.action}'
assert 'Chain Reaction' in result2.reason, f'Test 2 failed: reason does not contain Chain Reaction: {result2.reason}'
print('Test 2: Score 0.6 -> CLOSE_FULL (immediate_exit) ... OK', file=sys.stderr)

# Test 3: Disabled config -> HOLD (even with Score 1.0)
state3 = PositionState(
    entry_price=100.0,
    current_price=102.0,
    peak_price=102.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=1.0
)
result3 = evaluate_exit(state3, cfg_disabled)
assert result3.action == ExitAction.HOLD, f'Test 3 failed: expected HOLD (disabled), got {result3.action}'
print('Test 3: Disabled config -> HOLD ... OK', file=sys.stderr)

# Test 4: tighten_sl with PnL > panic_sl -> HOLD
state4 = PositionState(
    entry_price=100.0,
    current_price=105.0,  # +5% profit
    peak_price=105.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=0.6
)
result4 = evaluate_exit(state4, cfg_tighten_sl)
assert result4.action == ExitAction.HOLD, f'Test 4 failed: expected HOLD (PnL > panic_sl), got {result4.action}'
print('Test 4: tighten_sl with +5% -> HOLD ... OK', file=sys.stderr)

# Test 5: tighten_sl with PnL <= panic_sl -> CLOSE_FULL
state5 = PositionState(
    entry_price=100.0,
    current_price=98.0,  # -2% loss (panic_sl_pct)
    peak_price=98.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=0.6
)
result5 = evaluate_exit(state5, cfg_tighten_sl)
assert result5.action == ExitAction.CLOSE_FULL, f'Test 5 failed: expected CLOSE_FULL (PnL <= panic_sl), got {result5.action}'
print('Test 5: tighten_sl with -2% -> CLOSE_FULL ... OK', file=sys.stderr)

# Test 6: Boundary - Score exactly at threshold (0.5) should trigger
state6 = PositionState(
    entry_price=100.0,
    current_price=102.0,
    peak_price=102.0,
    elapsed_sec=30.0,
    remaining_pct=1.0,
    chain_reaction_score=0.5
)
result6 = evaluate_exit(state6, cfg_enabled_immediate)
assert result6.action == ExitAction.CLOSE_FULL, f'Test 6 failed: expected CLOSE_FULL (score >= threshold), got {result6.action}'
print('Test 6: Score 0.5 (threshold) -> CLOSE_FULL ... OK', file=sys.stderr)

print('[chain_reaction_smoke] OK', file=sys.stderr)
"
