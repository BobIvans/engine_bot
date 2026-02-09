"""
ingestion/dex/raydium/layouts.py

Raydium AMM v4 account layout definitions.

PR-U.1
"""
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Solana pubkey (32 bytes, base58 encoded)
PUBKEY_LENGTH = 32

# Raydium AMM v4 status values
AMM_STATUS_UNINITIALIZED = 0
AMM_STATUS_INITIALIZED = 1
AMM_STATUS_OPENED = 2
AMM_STATUS_STOPPED = 3


@dataclass
class PoolState:
    """
    Decoded Raydium AMM v4 Liquidity State.
    
    PR-U.1
    """
    # Account info
    status: int                    # u64: Pool status
    nonce: int                     # u64: Nonce forAuthority
    order_num: int                 # u64: Number of open orders
    depth: int                     # u64: Pool depth
    coin_decimals: int             # u64: Coin decimals
    pc_decimals: int               # u64: PC (quote) decimals
    state: int                     # u64: AMM state
    reset_flag: int                # u64: Reset flag
    
    # Mint addresses
    coin_mint: str                # Pubkey: Coin mint
    pc_mint: str                  # Pubkey: Quote mint
    lp_mint: str                  # Pubkey: LP token mint
    
    # Vault addresses
    coin_vault: str               # Pubkey: Coin vault
    pc_vault: str                 # Pubkey: PC vault
    
    # Authority
    authority: str                 # Pubkey: AMM authority
    
    # Open orders (optional)
    open_orders: str               # Pubkey: Open orders address
    
    # Market info
    market: str                    # Pubkey: Serum market
    market_program: str           # Pubkey: Market program
    
    # Target orders
    target_orders: str             # Pubkey: Target orders
    
    # Quote decimal
    quote_decimals: int            # u64: Quote decimals
    
    # Padding / Reserved
    padding: int                   # u64
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "nonce": self.nonce,
            "order_num": self.order_num,
            "depth": self.depth,
            "coin_decimals": self.coin_decimals,
            "pc_decimals": self.pc_decimals,
            "state": self.state,
            "reset_flag": self.reset_flag,
            "coin_mint": self.coin_mint,
            "pc_mint": self.pc_mint,
            "lp_mint": self.lp_mint,
            "coin_vault": self.coin_vault,
            "pc_vault": self.pc_vault,
            "authority": self.authority,
            "open_orders": self.open_orders,
            "market": self.market,
            "market_program": self.market_program,
            "target_orders": self.target_orders,
            "quote_decimals": self.quote_decimals,
            "padding": self.padding,
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self.status == AMM_STATUS_INITIALIZED
    
    @property
    def is_opened(self) -> bool:
        """Check if pool is open for trading."""
        return self.status == AMM_STATUS_OPENED
    
    def get_status_string(self) -> str:
        """Get human-readable status."""
        status_map = {
            AMM_STATUS_UNINITIALIZED: "UNINITIALIZED",
            AMM_STATUS_INITIALIZED: "INITIALIZED",
            AMM_STATUS_OPENED: "OPENED",
            AMM_STATUS_STOPPED: "STOPPED",
        }
        return status_map.get(self.status, f"UNKNOWN({self.status})")


def pubkey_to_string(data: bytes) -> str:
    """Convert 32-byte pubkey to base58 string."""
    import base58
    return base58.b58encode(data).decode('utf-8')


def parse_pubkey(data: bytes, offset: int) -> str:
    """Parse a pubkey from data at offset."""
    return pubkey_to_string(data[offset:offset + PUBKEY_LENGTH])


# Raydium AMM v4 layout
# Based on: https://github.com/raydium-io/raydium-amm/blob/master/program/src/state.rs
AMM_V4_LAYOUT = struct.Struct(
    # Format: 8-byte discriminator is skipped, then:
    # 8 x u64 (status, nonce, order_num, depth, coin_decimals, pc_decimals, state, reset_flag)
    # 9 x 32-byte pubkeys (coin_mint, pc_mint, lp_mint, coin_vault, pc_vault, authority, open_orders, market, market_program, target_orders)
    # 4 x u64 (quote_decimals, padding, padding2, padding3)
    '8sQ9Q32s32s32s32s32s32s32s32s32s4Q'
)


def decode_pool_state(data: bytes) -> PoolState:
    """
    Decode Raydium AMM v4 pool state from raw bytes.
    
    Args:
        data: Raw account data (bytes)
        
    Returns:
        PoolState object
        
    Raises:
        ValueError: If data is too short
    """
    if len(data) < 8 + AMM_V4_LAYOUT.size:
        raise ValueError(
            f"Data too short: got {len(data)} bytes, need at least {8 + AMM_V4_LAYOUT.size}"
        )
    
    # Skip 8-byte discriminator at the beginning
    raw_data = data[8:]
    
    if len(raw_data) < AMM_V4_LAYOUT.size:
        raise ValueError(
            f"Data too short after skipping discriminator: got {len(raw_data)}, "
            f"need {AMM_V4_LAYOUT.size}"
        )
    
    # Unpack the layout
    unpacked = AMM_V4_LAYOUT.unpack(raw_data)
    
    # Parse pubkeys
    offset = 0
    
    status = unpacked[offset]; offset += 1
    nonce = unpacked[offset]; offset += 1
    order_num = unpacked[offset]; offset += 1
    depth = unpacked[offset]; offset += 1
    coin_decimals = unpacked[offset]; offset += 1
    pc_decimals = unpacked[offset]; offset += 1
    state = unpacked[offset]; offset += 1
    reset_flag = unpacked[offset]; offset += 1
    
    coin_mint = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    pc_mint = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    lp_mint = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    coin_vault = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    pc_vault = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    authority = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    open_orders = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    market = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    market_program = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    target_orders = parse_pubkey(raw_data, offset); offset += PUBKEY_LENGTH
    
    quote_decimals = unpacked[offset]; offset += 1
    padding = unpacked[offset]
    
    return PoolState(
        status=status,
        nonce=nonce,
        order_num=order_num,
        depth=depth,
        coin_decimals=coin_decimals,
        pc_decimals=pc_decimals,
        state=state,
        reset_flag=reset_flag,
        coin_mint=coin_mint,
        pc_mint=pc_mint,
        lp_mint=lp_mint,
        coin_vault=coin_vault,
        pc_vault=pc_vault,
        authority=authority,
        open_orders=open_orders,
        market=market,
        market_program=market_program,
        target_orders=target_orders,
        quote_decimals=quote_decimals,
        padding=padding,
    )


def decode_base64(data: str) -> bytes:
    """Decode base64 string to bytes."""
    import base64
    return base64.b64decode(data)


def decode_hex(data: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes.fromhex(data)


def guess_encoding_and_decode(data: str) -> PoolState:
    """
    Try to decode data, guessing the encoding.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        PoolState object
    """
    try:
        # Try base64 first
        return decode_pool_state(decode_base64(data))
    except Exception:
        pass
    
    try:
        # Try hex
        return decode_pool_state(decode_hex(data))
    except Exception as e:
        raise ValueError(f"Failed to decode data: {e}")


@dataclass
class VaultState:
    """Decoded token vault state (Token Account)."""
    mint: str                 # Pubkey
    owner: str               # Pubkey
    amount: int              # u64: Token amount
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mint": self.mint,
            "owner": self.owner,
            "amount": self.amount,
        }


# Token Account layout
TOKEN_ACCOUNT_LAYOUT = struct.Struct('32s32sQ')


def decode_vault_state(data: bytes) -> VaultState:
    """
    Decode token vault state.
    
    Args:
        data: Raw account data
        
    Returns:
        VaultState object
    """
    if len(data) < TOKEN_ACCOUNT_LAYOUT.size:
        raise ValueError(f"Data too short: got {len(data)}, need {TOKEN_ACCOUNT_LAYOUT.size}")
    
    unpacked = TOKEN_ACCOUNT_LAYOUT.unpack(data)
    
    return VaultState(
        mint=pubkey_to_string(unpacked[0]),
        owner=pubkey_to_string(unpacked[1]),
        amount=unpacked[2],
    )
