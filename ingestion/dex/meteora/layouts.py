"""
ingestion/dex/meteora/layouts.py

Meteora DLMM LbPair account layout definitions.

PR-U.3
"""
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Solana pubkey (32 bytes, base58 encoded)
PUBKEY_LENGTH = 32

# Meteora LbPair discriminator
# sha256("account:LbPair") = 0x5b5ab4a3...
LB_PAIR_DISCRIMINATOR = b"\x5b\x5a\xb4\xa3\x2f\x85\x94\x87"


@dataclass
class LbPairState:
    """
    Decoded Meteora DLMM LbPair state.
    
    PR-U.3
    """
    # Parameters
    bin_step: int                  # u16: Bin step (in basis points / 10000)
    base_factor: int               # u16: Base factor
    
    # Active bin
    active_id: int                # i32: Current active bin ID
    
    # Token mints
    token_x_mint: str            # Pubkey: Token X mint
    token_y_mint: str            # Pubkey: Token Y mint
    
    # Token vaults
    token_x_vault: str            # Pubkey: Token X vault
    token_y_vault: str           # Pubkey: Token Y vault
    
    # Oracle
    oracle: str                   # Pubkey: Oracle account
    
    # Token decimals
    token_x_decimals: int         # u8: Token X decimals
    token_y_decimals: int         # u8: Token Y decimals
    
    # Fee parameters
    searcher_fee: int             # u64: Fee for searchers
    withdraw_fee: int             # u64: Fee for withdrawals
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bin_step": self.bin_step,
            "base_factor": self.base_factor,
            "active_id": self.active_id,
            "token_x_mint": self.token_x_mint,
            "token_y_mint": self.token_y_mint,
            "token_x_vault": self.token_x_vault,
            "token_y_vault": self.token_y_vault,
            "oracle": self.oracle,
            "token_x_decimals": self.token_x_decimals,
            "token_y_decimals": self.token_y_decimals,
            "searcher_fee": self.searcher_fee,
            "withdraw_fee": self.withdraw_fee,
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self.active_id != 0


def pubkey_to_string(data: bytes) -> str:
    """Convert 32-byte pubkey to base58 string."""
    import base58
    return base58.b58encode(data).decode('utf-8')


def parse_pubkey(data: bytes, offset: int) -> str:
    """Parse a pubkey from data at offset."""
    return pubkey_to_string(data[offset:offset + PUBKEY_LENGTH])


# Meteora LbPair account layout (without discriminator)
# Based on: https://github.com/MeteoraAg/dlmm-sdk/blob/main/idl/lb_pair.json
LB_PAIR_LAYOUT = struct.Struct(
    'H'       # bin_step: u16
    'H'       # base_factor: u16
    'i'       # active_id: i32 (signed)
    'Q'       # bin_step_seed: u64
    'Q'       # padding1: u64
    '32s'     # token_x_mint: Pubkey
    '32s'     # token_y_mint: Pubkey
    '32s'     # token_x_vault: Pubkey
    '32s'     # token_y_vault: Pubkey
    '32s'     # oracle: Pubkey
    'B'       # token_x_decimals: u8
    'B'       # token_y_decimals: u8
    '6x'      # padding: 6 bytes
    'Q'       # searcher_fee: u64
    'Q'       # withdraw_fee: u64
)

# LAYOUT_SIZE is the size of the struct without discriminator
# Calculation: H(2) + H(2) + i(4) + Q(8) + Q(8) + 32s*5(160) + B(1) + B(1) + 6x(6) + Q(8) + Q(8) = 208
LAYOUT_SIZE = 208

# Pubkey offset in raw_data (after skipping discriminator)
PUBKEY_OFFSETS = {
    'token_x_mint': 16,    # After: H(2) + H(2) + i(4) + Q(8) = 16
    'token_y_mint': 48,    # 16 + 32 = 48
    'token_x_vault': 80,   # 48 + 32 = 80
    'token_y_vault': 112,  # 80 + 32 = 112
    'oracle': 144,         # 112 + 32 = 144
}


def decode_lb_pair(data: bytes) -> LbPairState:
    """
    Decode Meteora LbPair state from raw bytes.
    
    Args:
        data: Raw account data (bytes) - includes 8-byte discriminator
        
    Returns:
        LbPairState object
        
    Raises:
        ValueError: If data is too short or invalid
    """
    if len(data) < 8 + LAYOUT_SIZE:
        raise ValueError(
            f"Data too short: got {len(data)} bytes, need at least {8 + LAYOUT_SIZE}"
        )
    
    # Skip discriminator
    raw_data = data[8:]
    
    if len(raw_data) < LAYOUT_SIZE:
        raise ValueError(
            f"Data too short after skipping discriminator: got {len(raw_data)}, "
            f"need {LAYOUT_SIZE}"
        )
    
    # Unpack the layout
    unpacked = LB_PAIR_LAYOUT.unpack(raw_data)
    
    # Parse fields (indices start from 0 since we skipped discriminator)
    bin_step = unpacked[0]
    base_factor = unpacked[1]
    active_id = unpacked[2]
    
    # Token mints at fixed offsets (from PUBKEY_OFFSETS)
    token_x_mint = parse_pubkey(raw_data, PUBKEY_OFFSETS['token_x_mint'])
    token_y_mint = parse_pubkey(raw_data, PUBKEY_OFFSETS['token_y_mint'])
    token_x_vault = parse_pubkey(raw_data, PUBKEY_OFFSETS['token_x_vault'])
    token_y_vault = parse_pubkey(raw_data, PUBKEY_OFFSETS['token_y_vault'])
    oracle = parse_pubkey(raw_data, PUBKEY_OFFSETS['oracle'])
    
    token_x_decimals = unpacked[10]  # index 10
    token_y_decimals = unpacked[11]  # index 11
    
    searcher_fee = unpacked[12]  # index 12
    withdraw_fee = unpacked[13]  # index 13
    
    return LbPairState(
        bin_step=bin_step,
        base_factor=base_factor,
        active_id=active_id,
        token_x_mint=token_x_mint,
        token_y_mint=token_y_mint,
        token_x_vault=token_x_vault,
        token_y_vault=token_y_vault,
        oracle=oracle,
        token_x_decimals=token_x_decimals,
        token_y_decimals=token_y_decimals,
        searcher_fee=searcher_fee,
        withdraw_fee=withdraw_fee,
    )


def decode_base64(data: str) -> bytes:
    """Decode base64 string to bytes."""
    import base64
    return base64.b64decode(data)


def decode_hex(data: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes.fromhex(data)


def guess_encoding_and_decode(data: str) -> LbPairState:
    """
    Try to decode data, guessing the encoding.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        LbPairState object
    """
    try:
        return decode_lb_pair(decode_base64(data))
    except Exception:
        pass
    
    try:
        return decode_lb_pair(decode_hex(data))
    except Exception as e:
        raise ValueError(f"Failed to decode data: {e}")
