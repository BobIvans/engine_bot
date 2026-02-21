#!/bin/bash
# scripts/exits_smoke.sh
# Smoke test for Aggressive Exits logic (PR-E.2)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() {
  echo -e "${RED}[exits_smoke] FAIL: $*${NC}" >&2
  exit 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[overlay_lint] running exits smoke..." >&2

# Test: Run Python tests for aggressive exits
python3 << 'PYEOF'
import sys
sys.path.insert(0, "${ROOT_DIR}")

from strategy.exits import (
    PositionState,
    ExitSignal,
    ExitAction,
    evaluate_exit,
    check_aggressive_trigger,
    calculate_trailing_stop,
)

import yaml

# Load config
with open("${ROOT_DIR}/integration/fixtures/config/aggressive_exits.yaml", "r") as f:
    cfg = yaml.safe_load(f)

print("[exits_smoke] Testing aggressive trigger detection...")

# Test 1: Check aggressive trigger NOT triggered for small price change
entry_price = 100.0

# Simulate: Price +1% at t=5s (should NOT trigger - need 3% in 15s)
state1 = PositionState(
    entry_price=entry_price,
    current_price=101.0,  # +1%
    peak_price=101.0,
    elapsed_sec=5.0,
    mode="U",
)

trigger1 = check_aggressive_trigger(
    current_price=state1.current_price,
    entry_price=state1.entry_price,
    elapsed_sec=state1.elapsed_sec,
    current_mode=state1.mode,
    cfg=cfg,
)

assert trigger1 is None, f"Tick 1 should NOT trigger aggressive mode, got {trigger1}"
print("  Tick 1 (+1% at 5s): HOLD - PASS")

# Test 2: Check aggressive trigger DOES trigger
# Simulate: Price +3.5% at t=10s (should trigger - 3%+ in <15s)
state2 = PositionState(
    entry_price=entry_price,
    current_price=103.5,  # +3.5%
    peak_price=103.5,
    elapsed_sec=10.0,
    mode="U",
)

trigger2 = check_aggressive_trigger(
    current_price=state2.current_price,
    entry_price=state2.entry_price,
    elapsed_sec=state2.elapsed_sec,
    current_mode=state2.mode,
    cfg=cfg,
)

assert trigger2 is not None, "Tick 2 should trigger aggressive mode"
assert trigger2["new_mode"] == "U_aggr", f"Expected U_aggr, got {trigger2['new_mode']}"
assert abs(trigger2["partial_pct"] - 0.4) < 0.01, f"Expected partial 0.4, got {trigger2['partial_pct']}"
print(f"  Tick 2 (+3.5% at 10s): TRIGGER {trigger2['new_mode']} partial={trigger2['partial_pct']} - PASS")

# Test 3: Evaluate exit with trigger
signal3 = evaluate_exit(state2, cfg)
assert signal3.action == ExitAction.PARTIAL_EXIT, f"Expected PARTIAL_EXIT, got {signal3.action}"
assert signal3.qty_pct == 0.4, f"Expected qty_pct 0.4, got {signal3.qty_pct}"
assert signal3.new_mode == "U_aggr", f"Expected new_mode U_aggr, got {signal3.new_mode}"
print(f"  Exit signal: {signal3.action.value} {signal3.qty_pct*100:.0f}% -> {signal3.new_mode} - PASS")

# Test 4: Trailing stop calculation
peak_price = 110.0  # Price went to +10%
trail_stop = calculate_trailing_stop(peak_price=peak_price, trail_pct=0.12)
expected_stop = 110.0 * (1 - 0.12)  # 96.8
assert abs(trail_stop - expected_stop) < 0.01, f"Expected {expected_stop}, got {trail_stop}"
print(f"  Trailing stop from peak {peak_price}: {trail_stop:.2f} (12% trail) - PASS")

# Test 5: Aggressive mode with trailing stop hit
# State: U_aggr mode, partial taken, peak at 110, now at 97 (below 96.8 trail stop)
state5 = PositionState(
    entry_price=entry_price,
    current_price=97.0,
    peak_price=110.0,
    elapsed_sec=25.0,
    mode="U_aggr",
    partial_taken=True,
)

signal5 = evaluate_exit(state5, cfg)
assert signal5.action == ExitAction.TRAIL_STOP, f"Expected TRAIL_STOP, got {signal5.action}"
assert signal5.qty_pct == 1.0, f"Expected full exit, got {signal5.qty_pct}"
print(f"  Trail stop exit: {signal5.action.value} - PASS")

# Test 6: Verify trailing stop NOT hit if price still above trigger
# State: U_aggr mode, partial taken, peak at 110, now at 100 (above 96.8 trail stop)
state6 = PositionState(
    entry_price=entry_price,
    current_price=100.0,
    peak_price=110.0,
    elapsed_sec=30.0,
    mode="U_aggr",
    partial_taken=True,
)

signal6 = evaluate_exit(state6, cfg)
assert signal6.action == ExitAction.HOLD, f"Expected HOLD, got {signal6.action}"
print(f"  No trailing stop (price {state6.current_price} > trigger 96.8): HOLD - PASS")

print("\n[exits_smoke] All aggressive exit tests passed!")
PYEOF

echo -e "${GREEN}[exits_smoke] OK ✅${NC}" >&2

exit 0
