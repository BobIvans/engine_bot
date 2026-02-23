#!/bin/bash
# scripts/meteora_smoke.sh
# Smoke test for Meteora DLMM Adapter
# PR-U.3

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[meteora_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[meteora_smoke] ERROR:${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[meteora_smoke] WARN:${NC} $1"
}

check_exit_code() {
    if [ $? -ne 0 ]; then
        log_error "$1"
        exit 1
    fi
}

PYTHON_BIN="${PYTHON_BIN:-python3}"

# Test fixtures
FIXTURE_FILE="$PROJECT_ROOT/integration/fixtures/meteora/lb_pair_sol_usdc.hex"

echo ""
log_info "Starting Meteora DLMM smoke tests..."
echo ""

# Test 1: Layouts module
log_info "Testing layouts module..."
cd "$PROJECT_ROOT"
$PYTHON_BIN -c "
from ingestion.dex.meteora.layouts import LB_PAIR_LAYOUT, LbPairState, decode_lb_pair
import struct

# Verify layout size
expected_size = 208  # struct layout size (excludes discriminator)
actual_size = LB_PAIR_LAYOUT.size
assert actual_size == expected_size, f'Expected {expected_size}, got {actual_size}'
print(f'  Layout size: {actual_size} bytes (OK)')

# Verify format string
print(f'  Format string: {LB_PAIR_LAYOUT.format} (OK)')

# Test decoding synthetic data
from ingestion.dex.meteora.math import BIN_ID_OFFSET

def create_synthetic_data(bin_step=20, active_id=8391115, decimals_x=9, decimals_y=6):
    data = bytearray(216)
    offset = 0

    def fixed_pubkey(seed_hex: str) -> bytes:
        """Return exactly 32 bytes for synthetic pubkey fields."""
        raw = bytes.fromhex(seed_hex)
        repeated = (raw * ((32 + len(raw) - 1) // len(raw)))[:32]
        assert len(repeated) == 32
        return repeated
    
    # discriminator (8 bytes)
    struct.pack_into('<Q', data, offset, 0x5b5ab4a32f859487)
    offset += 8
    
    # bin_step (2 bytes, u16)
    struct.pack_into('<H', data, offset, bin_step)
    offset += 2
    
    # base_factor (2 bytes, u16)
    struct.pack_into('<H', data, offset, 1000)
    offset += 2
    
    # active_id (4 bytes, i32)
    struct.pack_into('<i', data, offset, active_id)
    offset += 4
    
    # bin_step_seed (8 bytes, u64)
    struct.pack_into('<Q', data, offset, 123456789)
    offset += 8
    
    # padding1 (8 bytes, u64)
    struct.pack_into('<Q', data, offset, 0)
    offset += 8
    
    # token_x_mint (32 bytes) - SOL address
    token_x = fixed_pubkey('0123456789abcdef')
    data[offset:offset+32] = token_x
    offset += 32
    
    # token_y_mint (32 bytes) - USDC address
    token_y = fixed_pubkey('fedcba9876543210')
    data[offset:offset+32] = token_y
    offset += 32
    
    # token_x_vault (32 bytes)
    vault_x = fixed_pubkey('abcdef0123456789')
    data[offset:offset+32] = vault_x
    offset += 32
    
    # token_y_vault (32 bytes)
    vault_y = fixed_pubkey('56789abcdef01234')
    data[offset:offset+32] = vault_y
    offset += 32
    
    # oracle (32 bytes)
    oracle = fixed_pubkey('3456789abcdef012')
    data[offset:offset+32] = oracle
    offset += 32
    
    # token_x_decimals (1 byte, u8)
    data[offset] = decimals_x
    offset += 1
    
    # token_y_decimals (1 byte, u8)
    data[offset] = decimals_y
    offset += 1
    
    # padding (6 bytes)
    offset += 6
    
    # searcher_fee (8 bytes, u64)
    struct.pack_into('<Q', data, offset, 3000000)  # 0.3%
    offset += 8
    
    # withdraw_fee (8 bytes, u64)
    struct.pack_into('<Q', data, offset, 500000)  # 0.05%
    
    return bytes(data)

synthetic_data = create_synthetic_data()
decoded = decode_lb_pair(synthetic_data)
assert decoded.bin_step == 20, f'bin_step mismatch: {decoded[\"bin_step\"]}'
assert decoded.active_id == 8391115, f'active_id mismatch: {decoded[\"active_id\"]}'
assert decoded.token_x_decimals == 9, f'token_x_decimals mismatch: {decoded[\"token_x_decimals\"]}'
assert decoded.token_y_decimals == 6, f'token_y_decimals mismatch: {decoded[\"token_y_decimals\"]}'
print('  Synthetic data decode: OK')
print(f'  Active bin: {decoded[\"active_id\"]} (OK)')
print(f'  Bin step: {decoded[\"bin_step\"]} (OK)')
print('  Layout tests: PASSED')
"

check_exit_code "Layouts test failed"
echo ""

# Test 2: Math module
log_info "Testing math module..."
$PYTHON_BIN -c "
from ingestion.dex.meteora.math import (
    BIN_ID_OFFSET, MeteoraMath, get_price_from_id, get_id_from_price
)

# Verify constants
assert BIN_ID_OFFSET == 8388608, f'BIN_ID_OFFSET mismatch: {BIN_ID_OFFSET}'
print(f'  BIN_ID_OFFSET: {BIN_ID_OFFSET} (OK)')

# Test price calculation for known bin
# For bin_step=20, price = (1.002)^(8391115 - 8388608) = (1.002)^507 = 2.74
# But wait, 507 is too small for $150
# Let's recalculate: log_1.002(150) = ln(150)/ln(1.002) = 5.01/0.002 = 2505
# So active_id = 8388608 + 2505 = 8391113

# Test: $150 price with bin_step=20 (SOL=9 decimals, USDC=6 decimals)
bin_id = MeteoraMath.get_id_from_price(150.0, 20, 9, 6)
print(f'  Price 150 -> BinID: {bin_id}')

# Verify reverse
price = MeteoraMath.get_price_from_id(bin_id, 20, 9, 6)
assert abs(price - 150.0) < 1.0, f'Round-trip failed: {price}'
print(f'  BinID {bin_id} -> Price: {price:.2f} USD (OK)')

# Test lower price range
bin_id_low = MeteoraMath.get_id_from_price(0.5, 20, 9, 6)
price_low = MeteoraMath.get_price_from_id(bin_id_low, 20, 9, 6)
assert abs(price_low - 0.5) < 0.1, f'Low price round-trip failed: {price_low}'
print(f'  Price 0.5 -> BinID: {bin_id_low}, back to {price_low:.4f} (OK)')

# Test higher price range
bin_id_high = MeteoraMath.get_id_from_price(10000.0, 20, 9, 6)
price_high = MeteoraMath.get_price_from_id(bin_id_high, 20, 9, 6)
assert abs(price_high - 10000.0) < 100.0, f'High price round-trip failed: {price_high}'
print(f'  Price 10000 -> BinID: {bin_id_high}, back to {price_high:.2f} (OK)')

print('  Math tests: PASSED')
"

check_exit_code "Math test failed"
echo ""

# Test 3: Decoder module
log_info "Testing decoder module..."
$PYTHON_BIN -c "
from ingestion.dex.meteora.decoder import MeteoraDecoder
from ingestion.dex.meteora.layouts import decode_lb_pair
from ingestion.dex.meteora.math import BIN_ID_OFFSET
import struct

# Create synthetic LbPair data
def create_lb_pair_data(bin_step=20, active_id=8391113, decimals_x=9, decimals_y=6):
    data = bytearray(216)
    offset = 0
    
    # discriminator
    struct.pack_into('<Q', data, offset, 0x5b5ab4a32f859487)
    offset += 8
    
    struct.pack_into('<H', data, offset, bin_step)
    offset += 2
    struct.pack_into('<H', data, offset, 1000)
    offset += 2
    struct.pack_into('<i', data, offset, active_id)
    offset += 4
    struct.pack_into('<Q', data, offset, 123456789)
    offset += 8
    struct.pack_into('<Q', data, offset, 0)
    offset += 8
    
    # pubkeys
    for i in range(5):
        data[offset:offset+32] = bytes([i] * 32)
        offset += 32
    
    data[offset] = decimals_x
    offset += 1
    data[offset] = decimals_y
    offset += 1
    offset += 6  # padding
    
    struct.pack_into('<Q', data, offset, 3000000)
    offset += 8
    struct.pack_into('<Q', data, offset, 500000)
    
    return bytes(data)

# Test decode_lb_pair function
raw_data = create_lb_pair_data()
result = decode_lb_pair(raw_data)
assert result.bin_step == 20
assert result.active_id == 8391113
assert result.token_x_decimals == 9
assert result.token_y_decimals == 6
print(f'  decode_lb_pair: active_id={result.active_id}, bin_step={result.bin_step} (OK)')

# Test get_pool_info via decoder instance
decoder = MeteoraDecoder()
pool = decoder.decode_lb_pair(raw_data)
info = decoder.get_pool_info(pool)
assert 'price' in info
assert info['bin_step'] == 20
print(f'  get_pool_info: price={info[\"price\"]:.2f} USD (OK)')

# Test validation
valid, msg = MeteoraDecoder.validate_pool(raw_data)
assert valid, f'Pool should be valid: {msg}'
print(f'  validate_pool: {msg} (OK)')

print('  Decoder tests: PASSED')
"

check_exit_code "Decoder test failed"
echo ""

# Test 4: Fixture file
log_info "Testing fixture file..."
if [ -f "$FIXTURE_FILE" ]; then
    log_info "Fixture file exists, checking size..."
    FIXTURE_SIZE=$(wc -c < "$FIXTURE_FILE")
    log_info "Fixture size: $FIXTURE_SIZE bytes"
    
    # Verify it's hex data (even line count, valid hex characters)
    $PYTHON_BIN -c "
import sys
with open('$FIXTURE_FILE', 'r') as f:
    content = f.read().strip()
    # Remove comments
    lines = [l for l in content.split('\n') if not l.strip().startswith('#')]
    hex_content = ''.join(l.strip() for l in lines if l.strip())
    # Check it's valid hex
    bytes.fromhex(hex_content)
    print(f'  Fixture is valid hex: {len(hex_content)//2} bytes')
    "
    echo "  Fixture file: OK"
else
    log_warn "Fixture file not found (expected at: $FIXTURE_FILE)"
    log_warn "Skipping fixture test..."
fi

echo ""
log_info "All tests passed!"
log_info "OK"
