"""
Pure logic for data ingestion and normalization.

Handles conversion of raw external data (e.g. Bitquery GraphQL responses)
into canonical TradeEvent format for internal processing.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any

# Platform program IDs
RAYDIUM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
JUPITER_PROGRAM_ID = "JUP6LkbZbjS1jKKwapnHNygxzwHrQ32NqwnVERy8ls"

# Reject reasons
REJECT_BITQUERY_SCHEMA_MISMATCH = "REJECT_BITQUERY_SCHEMA_MISMATCH"
REJECT_INVALID_PRICE = "REJECT_INVALID_PRICE"

# Mock SOL price for conversion (in real system this would come from oracle/config)
SOL_USD_PRICE = 100.0 


@dataclass
class TradeEvent:
    """Canonical trade event structure."""
    timestamp: int
    wallet: str
    mint: str
    amount: float      # Token amount
    price_usd: float   # Price per token in USD
    value_usd: float   # Total value in USD
    platform: str
    tx_hash: str
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "wallet": self.wallet,
            "mint": self.mint,
            "amount": self.amount,
            "price_usd": self.price_usd,
            "value_usd": self.value_usd,
            "platform": self.platform,
            "tx_hash": self.tx_hash
        }


def normalize_bitquery_trade(node: Dict[str, Any]) -> Tuple[Optional[TradeEvent], Optional[str]]:
    """
    Normalize a Bitquery GraphQL trade node into a TradeEvent.
    
    Args:
        node: Dictionary representing a 'DEXTrade' node from Bitquery response.
        
    Returns:
        Tuple of (TradeEvent, reject_reason). 
        If successful, TradeEvent is populated and reject_reason is None.
        If failed, TradeEvent is None and reject_reason is populated.
    """
    # 1. Validate required fields structure
    try:
        block = node.get("block", {})
        ts_str = block.get("timestamp", {}).get("unixtime")
        swaps = node.get("swaps", [])
        
        if not ts_str or not swaps:
            return None, REJECT_BITQUERY_SCHEMA_MISMATCH
            
        # We assume the first swap in the chain holds the relevant info for simple trades
        # In reality might need more complex parsing for multi-hop
        swap = swaps[0]
        
        account = swap.get("account", {})
        owner = account.get("owner", {}).get("address")
        
        token_account = swap.get("tokenAccount", {})
        mint = token_account.get("mint", {}).get("address")
        
        amount_in = swap.get("amountIn")
        amount_out = swap.get("amountOut")
        
        dex = swap.get("dex", {})
        program_id = dex.get("programId")
        tx_hash = node.get("transaction", {}).get("signature")
        
        if not all([ts_str, owner, mint, amount_in, amount_out, program_id, tx_hash]):
            return None, REJECT_BITQUERY_SCHEMA_MISMATCH
            
    except (AttributeError, TypeError):
        return None, REJECT_BITQUERY_SCHEMA_MISMATCH
        
    # 2. Convert types
    try:
        timestamp = int(ts_str)
        qty_token = float(amount_in)
        qty_payment = float(amount_out)
        
        if qty_token <= 0 or qty_payment <= 0:
            return None, REJECT_INVALID_PRICE
            
    except (ValueError, TypeError):
        return None, REJECT_BITQUERY_SCHEMA_MISMATCH
        
    # 3. Validation
    if timestamp <= 0:
        return None, REJECT_BITQUERY_SCHEMA_MISMATCH
        
    # 4. Map Platform
    if program_id == RAYDIUM_PROGRAM_ID:
        platform = "raydium"
    elif program_id == ORCA_PROGRAM_ID:
        platform = "orca"
    elif program_id == JUPITER_PROGRAM_ID:
        platform = "jupiter"
    else:
        platform = "unknown"
        
    # 5. Price Calculation
    # Assuming amountOut is in SOL (or stable) and we check against SOL_USD
    # Price per token = (Payment / TokenQty) * SOL_Price
    try:
        token_price_in_payment_unit = qty_payment / qty_token
        price_usd = token_price_in_payment_unit * SOL_USD_PRICE
        value_usd = qty_token * price_usd
        
        if price_usd <= 0:
            return None, REJECT_INVALID_PRICE
            
    except ZeroDivisionError:
        return None, REJECT_INVALID_PRICE
        
    # 6. Construct Event
    event = TradeEvent(
        timestamp=timestamp,
        wallet=owner,
        mint=mint,
        amount=qty_token,
        price_usd=price_usd,
        value_usd=value_usd,
        platform=platform,
        tx_hash=tx_hash
    )
    
    return event, None


# Flipside-specific constants (PR-Y.3)
FLIPSIDE_REJECT_SCHEMA_MISMATCH = "FLIPSIDE_SCHEMA_MISMATCH"
FLIPSIDE_REJECT_MISSING_FIELD = "FLIPSIDE_MISSING_REQUIRED_FIELD"
FLIPSIDE_REJECT_INVALID_PROGRAM_ID = "FLIPSIDE_INVALID_PROGRAM_ID"

# Platform program ID mappings for Flipside
PROGRAM_ID_TO_PLATFORM = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "orca",
    "JUP6LkbZbjS1jKKwapnHNygxzwHrQ32NqwnVERy8ls": "jupiter",
    "22Y43yTVxuUvsRKqL4cc4nkrGC1TqnBsvZ62U4U2CN4": "pumpfun",
    "Df6yfrKC5kHEzq1bRzj5zL5AKcFmqz6A4LZTKbwP2Q2": "moonshot",
    "CAMMCzo5YL8w4VFF1KVztvNZ3HWTA7raSqoLAeCYgzEt": "meteora",
}


def normalize_flipside_trade(row: Dict[str, Any]) -> Tuple[Optional[TradeEvent], Optional[str]]:
    """
    Normalize a Flipside trade row into a TradeEvent.
    
    Args:
        row: Dictionary representing a trade row from Flipside query result.
            Expected fields: block_timestamp, swapper, token_mint, token_amount, 
            usd_amount, program_id, tx_hash
            
    Returns:
        Tuple of (TradeEvent, reject_reason). 
        If successful, TradeEvent is populated and reject_reason is None.
        If failed, TradeEvent is None and reject_reason is populated.
    """
    # 1. Validate required fields
    required_fields = [
        "block_timestamp",
        "swapper",
        "token_mint",
        "token_amount",
        "usd_amount",
        "program_id",
        "tx_hash",
    ]
    
    for field in required_fields:
        if field not in row or row[field] is None:
            return None, FLIPSIDE_REJECT_MISSING_FIELD
    
    # 2. Extract values
    try:
        ts_str = row["block_timestamp"]
        wallet = row["swapper"]
        mint = row["token_mint"]
        token_amount = row["token_amount"]
        usd_amount = row["usd_amount"]
        program_id = row["program_id"]
        tx_hash = row["tx_hash"]
        
        # Handle optional fields
        price_per_token = row.get("price_per_token")
        
    except (KeyError, TypeError):
        return None, FLIPSIDE_REJECT_SCHEMA_MISMATCH
    
    # 3. Convert types
    try:
        # Parse timestamp (ISO format or Unix)
        if isinstance(ts_str, str):
            if "T" in ts_str:
                # ISO 8601 format
                from datetime import datetime
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                timestamp = int(dt.timestamp())
            else:
                timestamp = int(ts_str)
        else:
            timestamp = int(ts_str)
        
        qty_token = float(token_amount)
        qty_usd = float(usd_amount)
        
        if qty_token <= 0 or qty_usd < 0:
            return None, FLIPSIDE_REJECT_SCHEMA_MISMATCH
            
    except (ValueError, TypeError):
        return None, FLIPSIDE_REJECT_SCHEMA_MISMATCH
    
    # 4. Validate timestamp
    if timestamp <= 0:
        return None, FLIPSIDE_REJECT_SCHEMA_MISMATCH
    
    # 5. Map Platform
    platform = PROGRAM_ID_TO_PLATFORM.get(program_id, "unknown")
    
    # 6. Calculate price and value
    if price_per_token and price_per_token > 0:
        price_usd = float(price_per_token)
    elif qty_token > 0:
        price_usd = qty_usd / qty_token
    else:
        return None, FLIPSIDE_REJECT_INVALID_PROGRAM_ID
    
    value_usd = qty_token * price_usd
    
    # 7. Construct Event
    event = TradeEvent(
        timestamp=timestamp,
        wallet=wallet,
        mint=mint,
        amount=qty_token,
        price_usd=price_usd,
        value_usd=value_usd,
        platform=platform,
        tx_hash=tx_hash
    )
    
    return event, None


if __name__ == "__main__":
    # Test with sample Flipside data
    sample_row = {
        "block_timestamp": "2024-01-15T10:00:00Z",
        "swapper": "Wallet123",
        "token_mint": "So11111111111111111111111111111111111111112",
        "token_amount": 100.0,
        "usd_amount": 150.0,
        "program_id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        "tx_hash": "Tx1234567890abcdef",
    }
    
    event, reason = normalize_flipside_trade(sample_row)
    if event:
        print("Success:", event.to_dict())
    else:
        print("Failed:", reason)
