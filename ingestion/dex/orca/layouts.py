"""
ingestion/dex/orca/layouts.py

Orca Whirlpools CLMM account layout definitions.

PR-U.2
"""
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Solana pubkey (32 bytes, base58 encoded)
PUBKEY_LENGTH = 32

# Orca Whirlpool discriminator
WHIRLPOOL_DISCRIMINATOR = b"\x5b\x31\x26\x9f\x87\x46\x3b\x4f"


@dataclass
class WhirlpoolState:
    """
    Decoded Orca Whirlpool CLMM state.
    
    PR-U.2
    """
    # Account info
    whirlpools_config: str           # Pubkey: Whirlpools config account
    tick_spacing: int                # u16: Tick spacing
    tick_current_index: int           # i32: Current tick index
    sqrt_price: int                  # u128: Sqrt price (Q64.64)
    liquidity: int                   # u128: Active liquidity
    
    # Mint addresses
    token_mint_a: str               # Pubkey: Token A mint
    token_mint_b: str               # Pubkey: Token B mint
    
    # Token vaults (optional)
    token_vault_a: str              # Pubkey: Token A vault
    token_vault_b: str              # Pubkey: Token B vault
    
    # Oracle accounts (optional)
    oracle_a: str                    # Pubkey: Oracle A
    oracle_b: str                    # Pubkey: Oracle B
    
    # Token decimals
    token_decimal_a: int             # u8: Token A decimals
    token_decimal_b: int             # u8: Token B decimals
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "whirlpools_config": self.whirlpools_config,
            "tick_spacing": self.tick_spacing,
            "tick_current_index": self.tick_current_index,
            "sqrt_price": self.sqrt_price,
            "liquidity": self.liquidity,
            "token_mint_a": self.token_mint_a,
            "token_mint_b": self.token_mint_b,
            "token_vault_a": self.token_vault_a,
            "token_vault_b": self.token_vault_b,
            "oracle_a": self.oracle_a,
            "oracle_b": self.oracle_b,
            "token_decimal_a": self.token_decimal_a,
            "token_decimal_b": self.token_decimal_b,
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self.sqrt_price > 0 and self.liquidity > 0


def pubkey_to_string(data: bytes) -> str:
    """Convert 32-byte pubkey to base58 string."""
    import base58
    return base58.b58encode(data).decode('utf-8')


def parse_pubkey(data: bytes, offset: int) -> str:
    """Parse a pubkey from data at offset."""
    return pubkey_to_string(data[offset:offset + PUBKEY_LENGTH])


# Orca Whirlpool account layout
# Based on: https://github.com/orca-so/whirlpool/blob/main/programs/whirlpool/src/states/whirlpool.rs
WHIRLPOOL_LAYOUT = struct.Struct(
    '8s'      # discriminator: 8 bytes
    '32s'     # whirlpools_config: Pubkey
    'H'       # tick_spacing: u16
    'x'       # padding: 2 bytes (u16 alignment)
    'i'       # tick_current_index: i32
    'Q'       # sqrt_price_lower: u64 (not used in basic decode)
    'Q'       # sqrt_price_upper: u64 (not used in basic decode)
    'Q'       # padding2: u64
    'Q'       # liquidity: u64 (we read as part of full u128)
    '16s'     # liquidity_remaining: u128 (partial)
    '32s'     # token_mint_a: Pubkey
    '32s'     # token_mint_b: Pubkey
    '32s'     # token_vault_a: Pubkey
    '32s'     # token_vault_b: Pubkey
    'B'       # token_decimal_a: u8
    'B'       # token_decimal_b: u8
    '6x'      # padding: 6 bytes
    '32s'     # oracle_a: Pubkey (optional)
    '32s'     # oracle_b: Pubkey (optional)
)

# Simplified layout for core fields (when oracle not present)
WHIRLPOOL_CORE_LAYOUT = struct.Struct(
    '8s'      # discriminator: 8 bytes
    '32s'     # whirlpools_config: Pubkey
    'H'       # tick_spacing: u16
    'x'       # padding: 1 byte (for alignment)
    'i'       # tick_current_index: i32
    'Q'       # sqrt_price_lower64: u64
    'Q'       # sqrt_price_upper64: u64
    'Q'       # padding: u64
    'Q'       # liquidity: u64
    'Q'       # liquidity_extra: u64
    '32s'     # token_mint_a: Pubkey
    '32s'     # token_mint_b: Pubkey
    '32s'     # token_vault_a: Pubkey
    '32s'     # token_vault_b: Pubkey
    'B'       # token_decimal_a: u8
    'B'       # token_decimal_b: u8
)


def decode_whirlpool(data: bytes) -> WhirlpoolState:
    """
    Decode Orca Whirlpool state from raw bytes.
    
    Args:
        data: Raw account data (bytes)
        
    Returns:
        WhirlpoolState object
        
    Raises:
        ValueError: If data is too short or invalid
    """
    # First try core layout (smaller)
    if len(data) >= 8 + WHIRLPOOL_CORE_LAYOUT.size:
        try:
            return _decode_core_layout(data)
        except Exception:
            pass
    
    # Try full layout if we have enough data
    if len(data) >= 8 + WHIRLPOOL_LAYOUT.size:
        try:
            return _decode_full_layout(data)
        except Exception:
            pass
    
    raise ValueError(
        f"Data too short: got {len(data)} bytes, "
        f"need at least {8 + WHIRLPOOL_CORE_LAYOUT.size} for core layout"
    )


def _decode_core_layout(data: bytes) -> WhirlpoolState:
    """Decode using core layout (without oracles)."""
    # Skip discriminator
    raw_data = data[8:]
    
    unpacked = WHIRLPOOL_CORE_LAYOUT.unpack(raw_data)
    
    whirlpools_config = parse_pubkey(raw_data, 0)
    offset = 32
    
    tick_spacing = unpacked[1]
    tick_current_index = unpacked[2]
    
    # Reconstruct sqrt_price from two u64
    sqrt_price_lower = unpacked[3]
    sqrt_price_upper = unpacked[4]
    sqrt_price = (sqrt_price_upper << 64) | sqrt_price_lower
    
    # Reconstruct liquidity from two u64
    liquidity_lower = unpacked[6]
    liquidity_upper = unpacked[7]
    liquidity = (liquidity_upper << 64) | liquidity_lower
    
    offset = 40  # After: config(32) + spacing(2) + pad(1) + tick(4) + sqrt(16) + liq(16)
    
    token_mint_a = parse_pubkey(raw_data, offset); offset += 32
    token_mint_b = parse_pubkey(raw_data, offset); offset += 32
    token_vault_a = parse_pubkey(raw_data, offset); offset += 32
    token_vault_b = parse_pubkey(raw_data, offset); offset += 32
    
    token_decimal_a = unpacked[13]
    token_decimal_b = unpacked[14]
    
    return WhirlpoolState(
        whirlpools_config=whirlpools_config,
        tick_spacing=tick_spacing,
        tick_current_index=tick_current_index,
        sqrt_price=sqrt_price,
        liquidity=liquidity,
        token_mint_a=token_mint_a,
        token_mint_b=token_mint_b,
        token_vault_a=token_vault_a,
        token_vault_b=token_vault_b,
        oracle_a="",  # Not in core layout
        oracle_b="",  # Not in core layout
        token_decimal_a=token_decimal_a,
        token_decimal_b=token_decimal_b,
    )


def _decode_full_layout(data: bytes) -> WhirlpoolState:
    """Decode using full layout (with oracles)."""
    raw_data = data[8:]
    
    unpacked = WHIRLPOOL_LAYOUT.unpack(raw_data)
    
    whirlpools_config = parse_pubkey(raw_data, 0)
    offset = 32
    
    tick_spacing = unpacked[1]
    tick_current_index = unpacked[2]
    
    # Reconstruct sqrt_price from two u64
    sqrt_price_lower = unpacked[3]
    sqrt_price_upper = unpacked[4]
    sqrt_price = (sqrt_price_upper << 64) | sqrt_price_lower
    
    # Reconstruct liquidity from u64 + remaining
    liquidity_lower = unpacked[6]
    liquidity_extra = unpacked[7]
    # Combine: full_u128 = (extra << 64) | lower
    liquidity = (liquidity_extra << 64) | liquidity_lower
    
    offset = 40  # After: config(32) + spacing(2) + pad(1) + tick(4) + sqrt(16) + liq(16)
    
    token_mint_a = parse_pubkey(raw_data, offset); offset += 32
    token_mint_b = parse_pubkey(raw_data, offset); offset += 32
    token_vault_a = parse_pubkey(raw_data, offset); offset += 32
    token_vault_b = parse_pubkey(raw_data, offset); offset += 32
    
    token_decimal_a = unpacked[13]
    token_decimal_b = unpacked[14]
    
    offset = 152  # Skip to oracle positions
    
    oracle_a = parse_pubkey(raw_data, offset); offset += 32
    oracle_b = parse_pubkey(raw_data, offset)
    
    return WhirlpoolState(
        whirlpools_config=whirlpools_config,
        tick_spacing=tick_spacing,
        tick_current_index=tick_current_index,
        sqrt_price=sqrt_price,
        liquidity=liquidity,
        token_mint_a=token_mint_a,
        token_mint_b=token_mint_b,
        token_vault_a=token_vault_a,
        token_vault_b=token_vault_b,
        oracle_a=oracle_a,
        oracle_b=oracle_b,
        token_decimal_a=token_decimal_a,
        token_decimal_b=token_decimal_b,
    )


def decode_base64(data: str) -> bytes:
    """Decode base64 string to bytes."""
    import base64
    return base64.b64decode(data)


def decode_hex(data: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes.fromhex(data)


def guess_encoding_and_decode(data: str) -> WhirlpoolState:
    """
    Try to decode data, guessing the encoding.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        WhirlpoolState object
    """
    try:
        return decode_whirlpool(decode_base64(data))
    except Exception:
        pass
    
    try:
        return decode_whirlpool(decode_hex(data))
    except Exception as e:
        raise ValueError(f"Failed to decode data: {e}")
