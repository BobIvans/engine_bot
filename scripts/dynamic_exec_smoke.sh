#!/bin/bash
# scripts/dynamic_exec_smoke.sh
# PR-E.3 Dynamic TTL & Slippage Model - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"

echo "[dynamic_exec_smoke] Starting dynamic execution smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import json

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

from strategy.dynamic_adjustment import (
    calculate_dynamic_ttl,
    calculate_slippage_bps,
    extract_volatility,
)
from execution.sim_fill import simulate_fill, FillResult

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [dynamic] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [dynamic] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[dynamic_exec_smoke] Testing pure dynamic adjustment logic...", file=sys.stderr)

# Config with dynamic execution enabled
cfg_enabled = {
    "dynamic_execution": {
        "enabled": True,
        "ttl_vol_factor": 10.0,
        "min_ttl_ms": 500,
        "slippage_slope": 0.01,
        "slippage_vol_mult": 5.0,
    },
    "orders": {"ttl": {"default_ttl_sec": 120}},
    "slippage_model": {"model": "constant_bps", "constant_bps": 80},
}

# Config with dynamic execution disabled
cfg_disabled = {
    "dynamic_execution": {"enabled": False},
    "orders": {"ttl": {"default_ttl_sec": 120}},
    "slippage_model": {"model": "constant_bps", "constant_bps": 80},
}

# Test 1: Dynamic TTL - higher volatility = shorter TTL
base_ttl = 2000  # 2 seconds in ms
vol_low = 0.01
vol_high = 0.10

ttl_low = calculate_dynamic_ttl(base_ttl, vol_low, cfg_enabled)
ttl_high = calculate_dynamic_ttl(base_ttl, vol_high, cfg_enabled)

test_case("dynamic_ttl_low_vol", ttl_low == 2000)  # 2000 / (1 + 10*0.01) = 2000 / 1.1 = 1818
test_case("dynamic_ttl_high_vol", ttl_high < ttl_low, f"ttl_high={ttl_high}, ttl_low={ttl_low}")
test_case("dynamic_ttl_high_vol_shorter", ttl_high < base_ttl)
test_case("dynamic_ttl_min_floor", ttl_high >= 500)  # min_ttl_ms

# Test 2: Dynamic TTL - disabled returns base
ttl_disabled = calculate_dynamic_ttl(base_ttl, vol_high, cfg_disabled)
test_case("dynamic_ttl_disabled", ttl_disabled == base_ttl)

# Test 3: Dynamic slippage - higher volatility = higher slippage
base_bps = 10
size_usd = 100.0
liq_usd = 10000.0

slip_low = calculate_slippage_bps(base_bps, size_usd, liq_usd, vol_low, cfg_enabled)
slip_high = calculate_slippage_bps(base_bps, size_usd, liq_usd, vol_high, cfg_enabled)

test_case("slippage_low_vol", slip_low == base_bps)  # No impact at low vol
test_case("slippage_high_vol", slip_high > slip_low, f"slip_high={slip_high}, slip_low={slip_low}")
test_case("slippage_high_vol_higher", slip_high > base_bps)

# Test 4: Dynamic slippage - larger size = higher slippage
size_large = 1000.0
slip_large = calculate_slippage_bps(base_bps, size_large, liq_usd, vol_low, cfg_enabled)
test_case("slippage_size_impact", slip_large > slip_low)

# Test 5: Dynamic slippage - disabled returns base
slip_disabled = calculate_slippage_bps(base_bps, size_usd, liq_usd, vol_high, cfg_disabled)
test_case("slippage_disabled", slip_disabled == base_bps)

# Test 6: extract_volatility from trade extra
trade_extra = {"vol_30s": 0.05}
snapshot_extra = {}
vol = extract_volatility(trade_extra, snapshot_extra)
test_case("extract_vol_trade", vol == 0.05)

# Test 7: extract_volatility from snapshot extra (fallback)
trade_extra2 = {}
snapshot_extra2 = {"vol_30s": 0.03}
vol2 = extract_volatility(trade_extra2, snapshot_extra2)
test_case("extract_vol_snapshot", vol2 == 0.03)

# Test 8: extract_volatility returns 0 when both missing
vol3 = extract_volatility({}, {})
test_case("extract_vol_default", vol3 == 0.0)

print("[dynamic_exec_smoke] Testing simulate_fill with dynamic models...", file=sys.stderr)

# Test 9: simulate_fill with dynamic slippage
# Create a mock snapshot with liquidity
class MockSnapshot:
    liquidity_usd = 10000.0

result_low = simulate_fill(
    side="buy",
    mid_price=100.0,
    size_usd=100.0,
    snapshot=MockSnapshot(),
    execution_cfg=cfg_enabled,
    mode_ttl_sec=120,
    seed=42,
    vol_30s=0.01,
)

result_high = simulate_fill(
    side="buy",
    mid_price=100.0,
    size_usd=100.0,
    snapshot=MockSnapshot(),
    execution_cfg=cfg_enabled,
    mode_ttl_sec=120,
    seed=42,  # Same seed = same latency
    vol_30s=0.10,
)

test_case("sim_fill_dynamic_slippage", result_high.slippage_bps >= result_low.slippage_bps)
test_case("sim_fill_slippage_positive", result_high.slippage_bps > 0)

# Summary
print(f"\n[dynamic_exec_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[dynamic_exec_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[dynamic_exec_smoke] Smoke test completed." >&2
