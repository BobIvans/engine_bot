#!/bin/bash
#
# scripts/raydium_pool_smoke.sh
#
# Smoke test for Raydium Pool Decoder adapter
#
# PR-JU.2
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "Raydium Pool Decoder Smoke Test"
echo "PR-JU.2"
echo "========================================"

# Change to root directory
cd "$ROOT_DIR"

# Check Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Test 1: Import the module
echo "[1/4] Testing module import..."
python3 -c "
from strategy.amm_math import estimate_slippage_bps
from ingestion.sources.raydium_pool import load_fixture, estimate_slippage_for_trade
print('  ✓ Imports successful')
"

# Test 2: Load fixture and validate
echo "[2/4] Loading and validating fixture..."
python3 -c "
import json
from pathlib import Path
fixture_path = Path('integration/fixtures/execution/raydium_pool_sample.json')
with open(fixture_path) as f:
    pools = json.load(f)
    
assert len(pools) >= 2, 'Expected at least 2 pools in fixture'
print(f'  ✓ Loaded {len(pools)} pools from fixture')

for pool in pools:
    assert 'pool_address' in pool
    assert 'mint_x' in pool
    assert 'mint_y' in pool
    assert 'reserve_x' in pool
    assert 'reserve_y' in pool
    assert 'fee_tier_bps' in pool
    print(f'  ✓ Pool {pool[\"pool_address\"][:16]}... validated')
"

# Test 3: Slippage calculation with known values
echo "[3/4] Testing slippage calculations..."
python3 -c "
from strategy.amm_math import estimate_slippage_bps

# Test case: 1% of reserve should give ~100 bps slippage (simplified)
# Using WIF/SOL pool values from fixture
slippage = estimate_slippage_bps(
    pool_address='EpX5PrYUWY7WDyjkJ5o3e3Vf9Uo5J4o9H4VrnLWDmTFF',
    amount_in=10000000000,  # 1% of reserve_x (1000000000000 * 0.01)
    token_mint='85VBFQZC9TZkfaptBWqv14ALD9fJNuk9nz2DPvCGQq4x',
    reserve_in=1000000000000.0,
    reserve_out=50000000000.0,
    fee_bps=25
)
print(f'  ✓ 1% trade slippage: {slippage} bps')

# Test case: Negligible trade should have near-zero slippage
slippage_small = estimate_slippage_bps(
    pool_address='test',
    amount_in=1000000,  # Very small
    token_mint='test',
    reserve_in=1000000000000.0,
    reserve_out=50000000000.0,
    fee_bps=25
)
print(f'  ✓ Small trade slippage: {slippage_small} bps')

# Test case: Large trade (10% of reserve) should have higher slippage
slippage_large = estimate_slippage_bps(
    pool_address='test',
    amount_in=100000000000,  # 10% of reserve_x
    token_mint='test',
    reserve_in=1000000000000.0,
    reserve_out=50000000000.0,
    fee_bps=25
)
print(f'  ✓ Large trade slippage: {slippage_large} bps')

# Validate monotonicity
assert slippage_small <= slippage, 'Small trade should have <= slippage than medium'
assert slippage <= slippage_large, 'Medium trade should have <= slippage than large'
print('  ✓ Slippage monotonicity validated')
"

# Test 4: End-to-end fixture + slippage
echo "[4/4] End-to-end fixture test..."
python3 -c "
import json
from pathlib import Path
from ingestion.sources.raydium_pool import load_fixture, estimate_slippage_for_trade

fixture_path = Path('integration/fixtures/execution/raydium_pool_sample.json')
pools = json.loads(fixture_path.read_text())

# Simulate WIF buy with 10M WIF
wif_pool = pools[0]
slippage = estimate_slippage_for_trade(
    pool_data=wif_pool,
    amount_in=10000000,
    input_mint=wif_pool['mint_x']
)
print(f'  ✓ WIF/SOL 10M WIF buy slippage: {slippage} bps')

# Simulate BONK sell of 1B BONK
bonk_pool = pools[1]
slippage_bonk = estimate_slippage_for_trade(
    pool_data=bonk_pool,
    amount_in=1000000000,
    input_mint=bonk_pool['mint_x']
)
print(f'  ✓ BONK/SOL 1B BONK sell slippage: {slippage_bonk} bps')
"

echo ""
echo "========================================"
echo "✓ All smoke tests passed!"
echo "========================================"
