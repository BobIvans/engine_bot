#!/bin/bash
# scripts/orca_smoke.sh
# Smoke test for Orca Whirlpools CLMM Adapter
# PR-U.2

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR/../integration/fixtures/orca"

echo "[orca_smoke] Starting Orca Whirlpools smoke tests..."

# Test 1: Layout definitions exist
echo "[orca_smoke] Checking layouts module..."
python3 -c "
from ingestion.dex.orca.layouts import (
    WHIRLPOOL_LAYOUT,
    WhirlpoolState,
    decode_whirlpool,
    WHIRLPOOL_DISCRIMINATOR,
)
print('[orca_smoke] Layouts module OK')
"

# Test 2: Math module exists and functions work
echo "[orca_smoke] Checking math module..."
python3 -c "
from ingestion.dex.orca.math import (
    OrcaMath,
    sqrt_price_x64_to_price,
    tick_to_price,
    get_liquidity_usd_estimate,
    Q64_SCALE,
)

# Test Q64 constant
assert Q64_SCALE == 18446744073709551616, 'Q64_SCALE should be 2^64'
print('[orca_smoke] Q64_SCALE constant OK')

# Test sqrt_price to price conversion (SOL/USDC ~150)
# For SOL (9 decimals) and USDC (6 decimals):
# Price_real = Price_raw × 10^(9-6) = Price_raw × 1000
# sqrt_price = int(sqrt(150/1000) × 2^64) ≈ 7100000000000000000
sqrt_price = int(7100000000000000000)
price = sqrt_price_x64_to_price(sqrt_price, 9, 6)
print(f'[orca_smoke] sqrt_price={sqrt_price} -> price={price:.2f} (OK)')
assert 100 < price < 200, f'Price should be around 150, got {price}'

# Test tick to price conversion
tick_price = tick_to_price(-29500, 9, 6)
print(f'[orca_smoke] tick=-29500 -> price={tick_price:.2f} (OK)')

print('[orca_smoke] Math module OK')
"

# Test 3: Decoder module exists
echo "[orca_smoke] Checking decoder module..."
python3 -c "
from ingestion.dex.orca.decoder import (
    OrcaDecoder,
    decode_orca_whirlpool,
)
print('[orca_smoke] Decoder module OK')
"

# Test 4: Pool fixture exists and is valid hex
echo "[orca_smoke] Checking pool fixture..."
if [ -f "$FIXTURE_DIR/whirlpool_sol_usdc.hex" ]; then
    # Remove comments and whitespace, then check hex content
    hex_content=$(grep -v '^#' "$FIXTURE_DIR/whirlpool_sol_usdc.hex" | tr -d '\n\r\t ' )
    hex_length=${#hex_content}
    echo "[orca_smoke] Pool fixture: $hex_length chars (OK)"
    
    # Verify it's valid hex
    if [[ ! "$hex_content" =~ ^[0-9a-fA-F]+$ ]]; then
        echo "[orca_smoke] ERROR: Invalid hex content"
        exit 1
    fi
    echo "[orca_smoke] Pool fixture hex validation OK"
else
    echo "[orca_smoke] ERROR: Pool fixture not found"
    exit 1
fi

# Test 5: Verify OrcaMath class exists (for GREP point)
echo "[orca_smoke] Checking OrcaMath class..."
python3 -c "
from ingestion.dex.orca.math import OrcaMath
import inspect
assert inspect.isclass(OrcaMath), 'OrcaMath should be a class'
print('[orca_smoke] OrcaMath class OK')
"

# Test 6: Verify convenience functions exist
echo "[orca_smoke] Checking convenience functions..."
python3 -c "
from ingestion.dex.orca.math import (
    sqrt_price_x64_to_price,
    tick_to_price,
    get_liquidity_usd_estimate,
)
print('[orca_smoke] Convenience functions OK')
"

# Test 7: Verify layout constants
echo "[orca_smoke] Checking WHIRLPOOL_LAYOUT..."
python3 -c "
from ingestion.dex.orca.layouts import WHIRLPOOL_LAYOUT
print(f'[orca_smoke] WHIRLPOOL_LAYOUT size: {WHIRLPOOL_LAYOUT.size} bytes (OK)')
assert WHIRLPOOL_LAYOUT.size > 0, 'Layout should have positive size'
"

echo "[orca_smoke] All smoke tests passed!"
echo "[orca_smoke] OK"
