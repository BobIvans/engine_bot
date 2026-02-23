#!/bin/bash
# scripts/allocation_smoke.sh
# Smoke test for Dynamic Mode Allocation
# PR-V.3

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[allocation_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[allocation_smoke] ERROR:${NC} $1" >&2
    exit 1
}

# Add project root to PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

echo ""
log_info "Starting Allocation smoke tests..."
echo ""

python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

import json
import os

from strategy.allocation import (
    ModeAllocator,
    AllocationConfig,
    AllocationResult,
    compute_allocation,
)
from integration.allocation_stage import load_config, run_allocation_stage

print("[allocation_smoke] Testing ModeAllocator...")
print("")

# Test 1: Basic allocation
print("[allocation_smoke] Test 1: Basic allocation...")

config = AllocationConfig(
    base_weights={'U': 0.2, 'S': 0.3, 'M': 0.25, 'L': 0.2, 'C': 0.05},
    vol_sensitivity=0.5,
    regime_sensitivity=0.5,
)

allocator = ModeAllocator(config)

# Normal market conditions
result = allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.5,
    regime_score=0.0,
)

assert isinstance(result, AllocationResult), "Should return AllocationResult"
assert result.version == "v1", f"Version should be v1, got {result.version}"
print(f"  Version: {result.version} (OK)")
print(f"  Allocations: {result.allocations} (OK)")
print("")

# Test 2: Invariant check - sum should equal equity
print("[allocation_smoke] Test 2: Invariant check (sum == equity)...")

total = sum(result.allocations.values())
assert abs(total - 1000.0) < 0.01, f"Sum {total} should equal 1000.0"
print(f"  Sum: {total:.2f} == 1000.00 (OK)")
print("")

# Test 3: High volatility test (risk-on)
print("[allocation_smoke] Test 3: High volatility (risk-on)...")

high_vol_result = allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.9,  # High vol
    regime_score=0.5,  # Bullish
)

# U+S should be higher in high vol
risk_on_high = high_vol_result.allocations.get('U', 0) + high_vol_result.allocations.get('S', 0)

print(f"  High vol U+S allocation: ${risk_on_high:.2f} (OK)")

# Compare with low vol
low_vol_result = allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.2,  # Low vol
    regime_score=0.5,
)

risk_on_low = low_vol_result.allocations.get('U', 0) + low_vol_result.allocations.get('S', 0)

print(f"  Low vol U+S allocation: ${risk_on_low:.2f} (OK)")

assert risk_on_high >= risk_on_low, "High vol should have >= U+S allocation"
print(f"  Volatility shift verified (OK)")
print("")

# Test 4: Bearish regime test (cash buffer)
print("[allocation_smoke] Test 4: Bearish regime (cash buffer)...")

bearish_result = allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.5,
    regime_score=-0.8,  # Very bearish
)

cash_bearish = bearish_result.allocations.get('C', 0)
print(f"  Cash allocation in bearish: ${cash_bearish:.2f} (OK)")

# Compare with bullish
bullish_result = allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.5,
    regime_score=0.8,  # Very bullish
)

cash_bullish = bullish_result.allocations.get('C', 0)
print(f"  Cash allocation in bullish: ${cash_bullish:.2f} (OK)")

assert cash_bearish >= cash_bullish, "Bearish should have >= cash allocation"
print(f"  Regime shift verified (OK)")
print("")

# Test 5: "Winter" scenario - U should be near minimum
print("[allocation_smoke] Test 5: Winter scenario...")

# Load config file
config_file = "integration/fixtures/allocation/weights.yaml"
assert os.path.exists(config_file), f"Config file not found: {config_file}"

file_config = load_config(config_file)
file_allocator = ModeAllocator(file_config)

winter_result = file_allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.1,  # Low vol
    regime_score=-0.5,  # Bearish
)

# In winter, U should be low
u_winter = winter_result.allocations.get('U', 0)
print(f"  Winter U allocation: ${u_winter:.2f} (OK)")

# Verify it's not excessive
assert u_winter < 200, f"Winter U allocation ${u_winter} should be < 200"
print(f"  Winter constraints verified (OK)")
print("")

# Test 6: "Bull Rush" scenario
print("[allocation_smoke] Test 6: Bull rush scenario...")

rush_result = file_allocator.compute_allocation(
    total_equity_usd=1000.0,
    volatility_score=0.9,  # High vol
    regime_score=0.8,  # Bullish
)

# In bull rush, U+S should be substantial
rush_risk_on = rush_result.allocations.get('U', 0) + rush_result.allocations.get('S', 0)
print(f"  Bull rush U+S allocation: ${rush_risk_on:.2f} (OK)")

# Should be more than half
assert rush_risk_on > 500, f"Bull rush U+S ${rush_risk_on} should be > 500"
print(f"  Bull rush verified (OK)")
print("")

# Test 7: Determinism check
print("[allocation_smoke] Test 7: Determinism check...")

result1 = file_allocator.compute_allocation(1000.0, 0.5, 0.0)
result2 = file_allocator.compute_allocation(1000.0, 0.5, 0.0)

assert result1.allocations == result2.allocations, "Same inputs should produce same outputs"
print(f"  Determinism verified (OK)")
print("")

# Test 8: Stage integration
print("[allocation_smoke] Test 8: Stage integration...")

stage_result = run_allocation_stage(
    equity_usd=1000.0,
    volatility=0.5,
    regime=0.0,
    config=file_config,
    dump_json=False,
)

assert stage_result.version == "v1", "Stage should return v1 result"
print(f"  Stage integration: OK")
print("")

print("[allocation_smoke] All allocation tests passed!")
print("[allocation_smoke] OK")
PYTEST
