"""ingestion/sources/helius.py

PR-M.1 Helius Webhook Parser for Enhanced Transactions.

Pure function to parse Helius Enhanced Transaction webhook payloads
and normalize them to canonical Trade format.

Helius docs: https://docs.helius.io/api/enhanced-transactions
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# Known Solana native tokens (for side detection)
NATIVE_MINTS = {
    "So11111111111111111111111111111111111111112",  # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "mSoLzYCxHdYgdzU8g5Qbh3ZwE9WdZ3xwVNTRB6Lf1oa",  # msOL
}


def parse_helius_enhanced_tx(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse Helius Enhanced Transaction webhook payload.

    Args:
        payload: Raw JSON dict from Helius webhook.

    Returns:
        Normalized trade dict matching integration/trade_schema.json,
        or None if payload should be skipped (non-SWAP type).
    """
    # Filter: Only process SWAP type transactions
    tx_type = payload.get("type", "")
    if tx_type != "SWAP":
        return None

    # Extract basic transaction info
    signature = payload.get("signature", "")
    timestamp = payload.get("timestamp", 0)
    fee_payer = payload.get("feePayer", "")

    # tokenTransfers contains the swap details
    token_transfers = payload.get("tokenTransfers", [])
    native_transfers = payload.get("nativeTransfers", [])

    if not token_transfers:
        return None

    # Find transfers involving the fee_payer wallet
    wallet_transfers = [
        t for t in token_transfers
        if t.get("fromUserAccount") == fee_payer or t.get("toUserAccount") == fee_payer
    ]

    if not wallet_transfers:
        return None

    # Identify the token mint (non-native) and native amount
    token_mint = None
    token_amount = 0.0
    native_amount = 0.0
    side = None

    for transfer in wallet_transfers:
        mint = transfer.get("mint", "")
        amount = float(transfer.get("tokenAmount", 0) or 0)
        from_user = transfer.get("fromUserAccount", "")
        to_user = transfer.get("toUserAccount", "")

        if mint in NATIVE_MINTS:
            # Native token transfer (SOL/USDC)
            native_amount = amount
            # If wallet is sending native, they're buying token (BUY)
            # If wallet is receiving native, they're selling token (SELL)
            if from_user == fee_payer:
                side = "BUY"
            else:
                side = "SELL"
        else:
            # Token mint (the actual token being traded)
            token_mint = mint
            token_amount = amount
            # If wallet is receiving this token, they're buying
            # If wallet is sending this token, they're selling
            if to_user == fee_payer:
                side = "BUY"
            else:
                side = "SELL"

    # If we didn't find a non-native token, skip
    if token_mint is None or token_amount <= 0:
        return None

    # Calculate price (quote amount / token amount)
    if native_amount > 0 and token_amount > 0:
        price = native_amount / token_amount
    else:
        price = 0.0

    # Calculate size_usd
    size_usd = price * token_amount

    # Build normalized trade record
    trade = {
        "ts": timestamp,
        "wallet": fee_payer,
        "mint": token_mint,
        "side": side,
        "price": price,
        "size_usd": size_usd,
        "tx_hash": signature,
        "source": "helius_webhook",
    }

    return trade
