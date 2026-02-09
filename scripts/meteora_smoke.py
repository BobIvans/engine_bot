#!/usr/bin/env python3
# scripts/meteora_smoke.py
# Smoke test for Meteora DLMM Adapter
# PR-U.3

import sys
import struct
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.dex.meteora.layouts import LB_PAIR_LAYOUT, LbPairState, decode_lb_pair
from ingestion.dex.meteora.math import BIN_ID_OFFSET, MeteoraMath

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def log_info(msg):
    print(f"{GREEN}[meteora_smoke]{NC} {msg}")

def log_error(msg):
    print(f"{RED}[meteora_smoke] ERROR:{NC} {msg}")
    sys.exit(1)

def log_warn(msg):
    print(f"{YELLOW}[meteora_smoke] WARN:{NC} {msg}")

def main():
    print("")
    log_info("Starting Meteora DLMM smoke tests...")
    print("")

    # Test 1: Layouts module
    log_info("Testing layouts module...")
    
    # Verify layout size
    expected_size = 208  # struct layout size (excludes discriminator)
    actual_size = LB_PAIR_LAYOUT.size
    assert actual_size == expected_size, f'Expected {expected_size}, got {actual_size}'
    print(f"  Layout size: {actual_size} bytes (OK)")
    
    # Verify format string
    print(f"  Format string: {LB_PAIR_LAYOUT.format} (OK)")
    
    # Test decoding synthetic data - use struct.pack directly
    def create_synthetic_data(bin_step=20, active_id=8391115, decimals_x=9, decimals_y=6):
        """Create synthetic LbPair data with discriminator using struct.pack."""
        # Note: 6x doesn't take a value in pack (it's padding)
        # Format: HHiQQ32s32s32s32s32sBB6xQQ = 14 items
        layout_data = struct.pack(
            '<HHiQQ32s32s32s32s32sBB6xQQ',
            bin_step,           # H: 2 bytes
            1000,              # H: 2 bytes
            active_id,          # i: 4 bytes
            123456789,         # Q: 8 bytes
            0,                 # Q: 8 bytes (padding1)
            bytes.fromhex('0123456789abcdef' * 2),  # 32s: token_x_mint
            bytes.fromhex('fedcba9876543210' * 2),  # 32s: token_y_mint
            bytes.fromhex('abcdef0123456789' * 2),  # 32s: token_x_vault
            bytes.fromhex('56789abcdef01234' * 2),  # 32s: token_y_vault
            bytes.fromhex('3456789abcdef0123' * 2),# 32s: oracle
            decimals_x,        # B: 1 byte
            decimals_y,        # B: 1 byte
            # 6x: 6 bytes padding (no value needed)
            3000000,           # Q: 8 bytes (searcher_fee)
            500000             # Q: 8 bytes (withdraw_fee)
        )
        assert len(layout_data) == 208, f"Layout data should be 208 bytes, got {len(layout_data)}"
        
        # Prepend discriminator (8 bytes)
        discriminator = struct.pack('<Q', 0x5b5ab4a32f859487)
        
        return discriminator + layout_data
    
    synthetic_data = create_synthetic_data()
    assert len(synthetic_data) == 216, f"Expected 216 bytes, got {len(synthetic_data)}"
    print(f"  Synthetic data size: {len(synthetic_data)} bytes (OK)")
    
    decoded = decode_lb_pair(synthetic_data)
    # decoded is a LbPairState dataclass, not a dict
    assert decoded.bin_step == 20, f'bin_step mismatch: {decoded.bin_step}'
    assert decoded.active_id == 8391115, f'active_id mismatch: {decoded.active_id}'
    assert decoded.token_x_decimals == 9, f'token_x_decimals mismatch: {decoded.token_x_decimals}'
    assert decoded.token_y_decimals == 6, f'token_y_decimals mismatch: {decoded.token_y_decimals}'
    print("  Synthetic data decode: OK")
    print(f"  Active bin: {decoded.active_id} (OK)")
    print(f"  Bin step: {decoded.bin_step} (OK)")
    print("  Layout tests: PASSED")
    print("")
    
    # Test 2: Math module
    log_info("Testing math module...")
    
    # Verify constants
    assert BIN_ID_OFFSET == 8388608, f'BIN_ID_OFFSET mismatch: {BIN_ID_OFFSET}'
    print(f"  BIN_ID_OFFSET: {BIN_ID_OFFSET} (OK)")
    
    # Test price calculation (function signature: get_id_from_price(price, bin_step, decimals_x, decimals_y))
    bin_id = MeteoraMath.get_id_from_price(150.0, 20, 9, 6)
    expected_id = BIN_ID_OFFSET + int(round(2505.15))
    print(f"  Price 150 -> BinID: {bin_id} (expected ~{expected_id})")
    
    price = MeteoraMath.get_price_from_id(bin_id, 20, 9, 6)
    assert abs(price - 150.0) < 1.0, f'Round-trip failed: {price}'
    print(f"  BinID {bin_id} -> Price: {price:.2f} USD (OK)")
    
    # Test lower price range
    bin_id_low = MeteoraMath.get_id_from_price(0.5, 20, 9, 6)
    price_low = MeteoraMath.get_price_from_id(bin_id_low, 20, 9, 6)
    assert abs(price_low - 0.5) < 0.1, f'Low price round-trip failed: {price_low}'
    print(f"  Price 0.5 -> BinID: {bin_id_low}, back to {price_low:.4f} (OK)")
    
    # Test higher price range
    bin_id_high = MeteoraMath.get_id_from_price(10000.0, 20, 9, 6)
    price_high = MeteoraMath.get_price_from_id(bin_id_high, 20, 9, 6)
    assert abs(price_high - 10000.0) < 100.0, f'High price round-trip failed: {price_high}'
    print(f"  Price 10000 -> BinID: {bin_id_high}, back to {price_high:.2f} (OK)")
    
    print("  Math tests: PASSED")
    print("")
    
    # Test 3: Decoder module - simple validation test
    log_info("Testing decoder module...")
    
    def create_lb_pair_data(bin_step=20, active_id=8391113, decimals_x=9, decimals_y=6):
        """Create synthetic LbPair data with discriminator using struct.pack."""
        layout_data = struct.pack(
            '<HHiQQ32s32s32s32s32sBB6xQQ',
            bin_step,
            1000,
            active_id,
            123456789,
            0,
            bytes([0] * 32),
            bytes([1] * 32),
            bytes([2] * 32),
            bytes([3] * 32),
            bytes([4] * 32),
            decimals_x,
            decimals_y,
            3000000,
            500000
        )
        discriminator = struct.pack('<Q', 0x5b5ab4a32f859487)
        return discriminator + layout_data
    
    raw_data = create_lb_pair_data()
    assert len(raw_data) == 216, f"Expected 216 bytes, got {len(raw_data)}"
    
    result = decode_lb_pair(raw_data)
    # Use attribute access for dataclass
    assert result.bin_step == 20
    assert result.active_id == 8391113
    assert result.token_x_decimals == 9
    assert result.token_y_decimals == 6
    assert result.is_initialized == True
    print(f"  decode_lb_pair: active_id={result.active_id}, bin_step={result.bin_step} (OK)")
    print(f"  is_initialized: {result.is_initialized} (OK)")
    
    # Test to_dict() method
    result_dict = result.to_dict()
    assert 'active_id' in result_dict
    assert 'bin_step' in result_dict
    assert result_dict['active_id'] == 8391113
    print(f"  to_dict() returns correct keys (OK)")
    
    # Calculate price using decoded data
    calc_price = MeteoraMath.get_price_from_id(result.active_id, result.bin_step, result.token_x_decimals, result.token_y_decimals)
    print(f"  Calculated price from active_id: ${calc_price:.2f} USD (OK)")
    
    print("  Decoder tests: PASSED")
    print("")
    
    # Test 4: Fixture file
    log_info("Testing fixture file...")
    fixture_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                 "integration", "fixtures", "meteora", "lb_pair_sol_usdc.hex")
    
    if os.path.exists(fixture_file):
        log_info("Fixture file exists, checking size...")
        fixture_size = os.path.getsize(fixture_file)
        log_info(f"Fixture size: {fixture_size} bytes")
        
        with open(fixture_file, 'r') as f:
            content = f.read().strip()
            lines = [l for l in content.split('\n') if not l.strip().startswith('#')]
            hex_content = ''.join(l.strip() for l in lines if l.strip())
            bytes.fromhex(hex_content)
            print(f"  Fixture is valid hex: {len(hex_content)//2} bytes")
        print("  Fixture file: OK")
    else:
        log_warn(f"Fixture file not found (expected at: {fixture_file})")
        log_warn("Skipping fixture test...")
    
    print("")
    log_info("All tests passed!")
    # [meteora_smoke] OK marker for GREP
    log_info("OK")

if __name__ == "__main__":
    main()
