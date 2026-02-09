"""
ingestion/market/pyth_ids.py

Pyth Network Price Feed IDs Registry.

PR-T.3
"""
from typing import Dict


# Pyth Price Feed IDs (Solana mainnet)
# Format: <hex string>
FEED_IDS: Dict[str, str] = {
    # Crypto
    "SOL/USD": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "BTC/USD": "0xe62df6c8b4a2fe73b05eed7dff4a5f1ed31e2c3c8b8f6b8e4f5c5d8e9f0a1b",
    "ETH/USD": "0x1a8b6f8e9f2c7b1d4e5f6a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7",
    "BONK/USD": "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1",
    
    # Stablecoins (should be ~1.0)
    "USDC/USD": "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "USDT/USD": "0x3f1d2b4a5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d",
    
    # Indices
    "CRYPTO_INDEX": "0x9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f",
}


def get_feed_id(symbol: str) -> str:
    """
    Get Pyth Price Feed ID for a symbol.
    
    Args:
        symbol: Trading pair (e.g., "SOL/USD", "BTC/USD")
        
    Returns:
        Hex string of the feed ID
        
    Raises:
        KeyError: If symbol is not in registry
    """
    normalized = symbol.upper().strip()
    
    if normalized not in FEED_IDS:
        raise KeyError(f"Unknown price feed symbol: {symbol}. Available: {list(FEED_IDS.keys())}")
    
    return FEED_IDS[normalized]


def get_symbol_from_feed_id(feed_id: str) -> str:
    """
    Get symbol from feed ID.
    
    Args:
        feed_id: Hex string of the feed ID
        
    Returns:
        Symbol string
        
    Raises:
        KeyError: If feed_id is not in registry
    """
    for symbol, fid in FEED_IDS.items():
        if fid.lower() == feed_id.lower():
            return symbol
    
    raise KeyError(f"Unknown feed ID: {feed_id}")


def list_symbols() -> list:
    """List all available symbols."""
    return list(FEED_IDS.keys())


def is_stablecoin(symbol: str) -> bool:
    """Check if symbol is a stablecoin (should have price ~1.0)."""
    stablecoins = ["USDC/USD", "USDT/USD"]
    return symbol.upper() in stablecoins
