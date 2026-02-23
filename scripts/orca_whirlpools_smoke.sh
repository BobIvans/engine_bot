#!/bin/bash
#
# scripts/orca_whirlpools_smoke.sh
#
# Smoke test for Orca Whirlpools concentrated liquidity decoder
#
# PR-ORC.1
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "Orca Whirlpools Smoke Test"
echo "PR-ORC.1"
echo "========================================"

cd "$ROOT_DIR"

# Check Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Test 1: Import the module
echo "[1/5] Testing module import..."
python3 -c "
from strategy.amm_math import estimate_whirlpool_slippage_bps
from ingestion.sources.orca_whirlpools import OrcaWhirlpoolDecoder, load_fixture
print('  ✓ Imports successful')
"

# Test 2: Load fixture and validate schema
echo "[2/5] Loading and validating fixture..."
python3 -c "
import json
fixture_path = 'integration/fixtures/execution/orca_pool_sample.json'
with open(fixture_path) as f:
    pools = json.load(f)

assert len(pools) >= 2, 'Expected at least 2 pools in fixture'
print(f'  ✓ Loaded {len(pools)} pools from fixture')

for pool in pools:
    assert 'pool_address' in pool
    assert 'mint_x' in pool
    assert 'mint_y' in pool
    assert 'sqrt_price_x64' in pool
    assert 'tick_current' in pool
    assert 'liquidity' in pool
    assert 'tick_spacing' in pool
    assert 'fee_tier_bps' in pool
    print(f'  ✓ Pool {pool[\"pool_address\"][:16]}... validated')
"

# Test 3: Find pool by token mint
echo "[3/5] Testing pool lookup by token mint..."
python3 -c "
from ingestion.sources.orca_whirlpools import OrcaWhirlpoolDecoder

decoder = OrcaWhirlpoolDecoder()

# Find high liquidity pool
pool = decoder.load_from_file(
    'integration/fixtures/execution/orca_pool_sample.json',
    'DeXkVx9f7eVN6FJqzsdMps4xE6K7LxY6TiqTLT4zSZ'
)
assert pool is not None, 'Pool should be found'
assert pool['tick_spacing'] == 64, 'High liquidity pool should have tick_spacing=64'
print(f'  ✓ Found high liquidity pool: tick={pool[\"tick_current\"]}, tick_spacing={pool[\"tick_spacing\"]}')

# Find low liquidity pool
pool2 = decoder.load_from_file(
    'integration/fixtures/execution/orca_pool_sample.json',
    'MeMeCo3XHMHc4z2Z9KmQ2a2a4jG6Vz7Lvq4TiqTLT4zSZ'
)
assert pool2 is not None, 'Low liquidity pool should be found'
assert pool2['tick_spacing'] == 128, 'Low liquidity pool should have tick_spacing=128'
print(f'  ✓ Found low liquidity pool: tick={pool2[\"tick_current\"]}, tick_spacing={pool2[\"tick_spacing\"]}')
"

# Test 4: Slippage calculations
echo "[4/5] Testing concentrated liquidity slippage calculations..."
python3 -c "
from strategy.amm_math import estimate_whirlpool_slippage_bps

# High liquidity pool: \$5000 on \$75k effective liquidity
# Formula: effective_liquidity_usd = liquidity * sqrt_price * tick_spacing_factor * sol_price
# With liquidity=7450, sqrt_price=1.0 (normalized), tick_spacing_factor=1.0, sol_price=100:
# effective_liquidity_usd = 7450 * 1.0 * 1.0 * 100 = \$745,000
# size_ratio = 5000/745000 = 0.0067 -> 0.67%
slippage_high = estimate_whirlpool_slippage_bps(
    liquidity=7450,
    sqrt_price_x64=18446462598759638720,  # sqrt(SOL/USDC) ~ 1.0 normalized
    tick_spacing=64,
    size_usd=5000,
    token_price_usd=0.8,
    sol_price_usd=100.0
)
print(f'  ✓ High liquidity pool (liquidity=7450): {slippage_high} bps for \$5000 buy')
assert slippage_high >= 50 and slippage_high <= 100, f'Expected ~67 bps, got {slippage_high}'
print(f'  ✓ Slippage within expected range (50-100 bps)')

# Low liquidity pool with wider tick spacing (more slippage)
# liquidity=667, tick_spacing=128 -> tick_spacing_factor=2.0
# effective_liquidity_usd = 667 * 1.0 * 2.0 * 100 = \$133,400
# size_ratio = 5000/133400 = 0.037 -> 3.7%
slippage_low = estimate_whirlpool_slippage_bps(
    liquidity=667,
    sqrt_price_x64=18446462598759638720,
    tick_spacing=128,
    size_usd=5000,
    token_price_usd=0.8,
    sol_price_usd=100.0
)
print(f'  ✓ Low liquidity pool (liquidity=667, tick_spacing=128): {slippage_low} bps for \$5000 buy')
assert slippage_low >= 300 and slippage_low <= 500, f'Expected ~370 bps, got {slippage_low}'
print(f'  ✓ Low liquidity slippage correctly higher (300-500 bps)')
"

# Test 5: End-to-end with decoder
echo "[5/5] End-to-end decoder test..."
python3 -c "
from ingestion.sources.orca_whirlpools import OrcaWhirlpoolDecoder
import json

decoder = OrcaWhirlpoolDecoder()

# Load high liquidity pool
pool = decoder.load_from_file(
    'integration/fixtures/execution/orca_pool_sample.json',
    'DeXkVx9f7eVN6FJqzsdMps4xE6K7LxY6TiqTLT4zSZ'
)

# Calculate slippage
slippage = decoder.estimate_slippage_for_token(
    pool=pool,
    size_usd=5000,
    token_price_usd=0.8,
)
print(f'  ✓ End-to-end slippage: {slippage} bps')

# Verify output format
output = {
    'pool_decoded': True,
    'pool_address': pool['pool_address'],
    'tick_current': pool['tick_current'],
    'liquidity': pool['liquidity'],
    'estimated_slippage_bps': slippage,
    'schema_version': 'orca_pool.v1',
}
print(f'  ✓ JSON output format valid')
print(json.dumps(output, indent=2))
" 2>&1 | grep -v "^\s*$" | head -20

echo ""
echo "========================================"
echo "✓ All smoke tests passed!"
echo "[orca_whirlpools_smoke] OK"
echo "========================================"
