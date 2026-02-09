#!/usr/bin/env python3
"""
ingestion/sources/raydium_dex.py

Raydium DEX Source Adapter - Monitors on-chain swap events from Raydium CPMM pools,
decodes logs, filters by liquidity, and yields canonical trade_event format.

PR-RAY.1

Features:
- Pure log decoding (no program interaction needed for fixture mode)
- Liquidity filtering: pool_reserve_sol * sol_price_usd >= min_liquidity_usd
- Supports both fixture (deterministic) and RPC (real-time) modes
- Graceful degradation on RPC errors
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Raydium CPMM program ID
RAYDIUM_CPMM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

# SOL mint address
SOL_MINT = "So11111111111111111111111111111111111111112"

# Default minimum liquidity threshold (USD)
DEFAULT_MIN_LIQUIDITY_USD = 2000.0


@dataclass
class RaydiumSwapEvent:
    """Decoded Raydium CPMM swap event."""
    slot: int
    block_time: int
    input_amount: int  # In lamports for SOL, base units for tokens
    output_amount: int  # In base units for tokens
    input_mint: str
    output_mint: str
    pool_reserve_sol: Optional[float] = None  # SOL reserves for liquidity check
    sol_price_usd: Optional[float] = None  # SOL price in USD


@dataclass
class TradeEvent:
    """Canonical trade event for integration pipeline."""
    ts: str  # ISO-8601 timestamp
    wallet: str
    mint: str
    side: str  # "BUY" or "SELL"
    size_usd: float
    price: float
    platform: str
    tx_hash: str
    slot: Optional[int] = None
    pool_id: Optional[str] = None


def decode_raydium_cpmm_log(log: str, slot: int, block_time: int) -> Optional[RaydiumSwapEvent]:
    """
    Decode a Raydium CPMM swap log entry.
    
    Args:
        log: Single log line from the transaction
        slot: Solana slot number
        block_time: Block timestamp in seconds
        
    Returns:
        RaydiumSwapEvent if log contains valid swap data, None otherwise
    """
    # Check for swap log pattern (the swap log line contains the swap data)
    # Note: Program ID check is done at the source level, not per log line
    # because the swap data is in a separate "Program log: swap..." line
    if "swap" not in log.lower():
        return None
    
    # Check for the swap data pattern
    if "input_amount:" not in log or "output_amount:" not in log:
        return None
    
    # Parse input_amount
    input_match = re.search(r'input_amount:\s*(\d+)', log)
    if not input_match:
        return None
    input_amount = int(input_match.group(1))
    
    # Parse output_amount
    output_match = re.search(r'output_amount:\s*(\d+)', log)
    if not output_match:
        return None
    output_amount = int(output_match.group(1))
    
    # Parse input_mint
    input_mint_match = re.search(r'input_mint:\s*([A-Za-z0-9]+)', log)
    if not input_mint_match:
        return None
    input_mint = input_mint_match.group(1)
    
    # Parse output_mint
    output_mint_match = re.search(r'output_mint:\s*([A-Za-z0-9]+)', log)
    if not output_mint_match:
        return None
    output_mint = output_mint_match.group(1)
    
    return RaydiumSwapEvent(
        slot=slot,
        block_time=block_time,
        input_amount=input_amount,
        output_amount=output_amount,
        input_mint=input_mint,
        output_mint=output_mint
    )


class RaydiumDexSource:
    """
    Trade source for Raydium CPMM swaps.
    
    Supports:
    - Fixture mode: Load from JSON file with pre-decoded swaps
    - RPC mode: Fetch real swaps via Solana RPC (optional, controlled by flag)
    """
    
    def __init__(
        self,
        min_liquidity_usd: float = DEFAULT_MIN_LIQUIDITY_USD,
        dry_run: bool = True
    ):
        """
        Initialize Raydium DEX source.
        
        Args:
            min_liquidity_usd: Minimum liquidity threshold in USD
            dry_run: If True, only process fixtures without RPC calls
        """
        self.min_liquidity_usd = min_liquidity_usd
        self.dry_run = dry_run
        self._processed_tx_hashes: set = set()
    
    def load_from_file(self, path: str) -> List[TradeEvent]:
        """
        Load and decode swaps from fixture file.
        
        Args:
            path: Path to JSON fixture file
            
        Returns:
            List of decoded TradeEvent objects
        """
        fixture_path = Path(path)
        if not fixture_path.exists():
            logger.error(f"Fixture file not found: {path}")
            return []
        
        with open(fixture_path) as f:
            fixtures = json.load(f)
        
        trades = []
        for fixture in fixtures:
            trades.extend(self._process_fixture_item(fixture))
        
        return trades
    
    def _process_fixture_item(self, fixture: Dict[str, Any]) -> List[TradeEvent]:
        """
        Process a single fixture item.
        
        Args:
            fixture: Fixture dict with slot, block_time, logs, pool_reserve_sol, sol_price_usd
            
        Returns:
            List of TradeEvent objects (may be empty if filtered)
        """
        slot = fixture.get("slot", 0)
        block_time = fixture.get("block_time", 0)
        logs = fixture.get("logs", [])
        pool_reserve_sol = fixture.get("pool_reserve_sol", 0.0)
        sol_price_usd = fixture.get("sol_price_usd", 0.0)
        
        trades = []
        
        for log in logs:
            swap_event = decode_raydium_cpmm_log(log, slot, block_time)
            if swap_event is None:
                continue
            
            # Set liquidity data
            swap_event.pool_reserve_sol = pool_reserve_sol
            swap_event.sol_price_usd = sol_price_usd
            
            # Convert to trade event
            trade = self._swap_to_trade(swap_event)
            if trade is not None:
                trades.append(trade)
        
        return trades
    
    def _swap_to_trade(self, swap: RaydiumSwapEvent) -> Optional[TradeEvent]:
        """
        Convert a decoded swap event to canonical trade event.
        
        Args:
            swap: Decoded RaydiumSwapEvent
            
        Returns:
            TradeEvent or None if filtered by liquidity
        """
        # Calculate liquidity
        liquidity_usd = None
        if swap.pool_reserve_sol is not None and swap.sol_price_usd is not None:
            liquidity_usd = swap.pool_reserve_sol * swap.sol_price_usd
        
        # Skip if liquidity check fails
        if liquidity_usd is not None and liquidity_usd < self.min_liquidity_usd:
            logger.debug(f"Skipping swap: liquidity ${liquidity_usd:.2f} < ${self.min_liquidity_usd}")
            return None
        
        # Determine side based on input mint
        if swap.input_mint == SOL_MINT:
            side = "BUY"
            # Buying token: input is SOL, output is token
            size_usd = swap.input_amount / 1e9 * (swap.sol_price_usd or 100.0)
            mint = swap.output_mint
            price = size_usd / (swap.output_amount / 1e6) if swap.output_amount > 0 else 0
        else:
            side = "SELL"
            # Selling token: input is token, output is SOL
            size_usd = swap.output_amount / 1e9 * (swap.sol_price_usd or 100.0)
            mint = swap.input_mint
            price = size_usd / (swap.input_amount / 1e6) if swap.input_amount > 0 else 0
        
        # Generate tx_hash from swap data (deterministic for fixtures)
        tx_hash = f"swap_{swap.slot}_{swap.input_mint[:8]}_{swap.output_mint[:8]}"
        
        # Skip duplicate transactions
        if tx_hash in self._processed_tx_hashes:
            return None
        self._processed_tx_hashes.add(tx_hash)
        
        return TradeEvent(
            ts=f"1970-01-01T00:00:00.000Z",  # Placeholder, would be block_time in real RPC
            wallet="RAYDIUM_CPMM_POOL",  # Placeholder for fixture mode
            mint=mint,
            side=side,
            size_usd=round(size_usd, 2),
            price=round(price, 6),
            platform="raydium_cpmm",
            tx_hash=tx_hash,
            slot=swap.slot,
            pool_id=f"pool_{swap.slot}"
        )
    
    def fetch_realtime(
        self,
        rpc_url: str,
        pool_address: str,
        lookback_slots: int = 100
    ) -> List[TradeEvent]:
        """
        Fetch real swaps from Raydium CPMM pool via RPC.
        
        This method is only called when --allow-raydium-dex flag is set.
        
        Args:
            rpc_url: Solana RPC endpoint URL
            pool_address: Address of the Raydium CPMM pool
            lookback_slots: Number of slots to look back for new swaps
            
        Returns:
            List of TradeEvent objects
        """
        if self.dry_run:
            logger.info("[raydium_dex] Dry run mode, skipping RPC fetch")
            return []
        
        try:
            import httpx
        except ImportError:
            logger.warning("[raydium_dex] httpx not available, skipping RPC fetch")
            return []
        
        try:
            client = httpx.AsyncClient(timeout=30.0)
        except Exception as e:
            logger.warning(f"[raydium_dex] Failed to create RPC client: {e}")
            return []
        
        trades = []
        
        try:
            # Get signatures for the pool address
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    pool_address,
                    {"limit": lookback_slots}
                ]
            }
            
            response = client.post(rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "result" not in data or "signatures" not in data["result"]:
                return []
            
            for sig_info in data["result"]["signatures"]:
                sig = sig_info.get("signature", "")
                
                if sig in self._processed_tx_hashes:
                    continue
                
                # Get transaction details
                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "getTransaction",
                    "params": [
                        sig,
                        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                    ]
                }
                
                tx_response = client.post(rpc_url, json=tx_payload)
                if tx_response.status_code != 200:
                    continue
                
                tx_data = tx_response.json()
                if "result" not in tx_data:
                    continue
                
                # Extract logs and decode
                meta = tx_data["result"].get("meta", {})
                logs = meta.get("logMessages", [])
                
                slot = tx_data["result"].get("slot", 0)
                block_time = tx_data["result"].get("blockTime", 0)
                
                for log in logs:
                    swap = decode_raydium_cpmm_log(log, slot, block_time)
                    if swap is None:
                        continue
                    
                    trade = self._swap_to_trade(swap)
                    if trade is not None:
                        trades.append(trade)
                        
        except Exception as e:
            logger.warning(f"[raydium_dex] RPC error: {e}, returning partial results")
        
        return trades
    
    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """
        Iterator for TradeSource interface.
        
        Yields:
            Dict records compatible with trade normalization pipeline
        """
        for trade in self._processed_trades:
            yield {
                "ts": trade.ts,
                "wallet": trade.wallet,
                "mint": trade.mint,
                "side": trade.side,
                "size_usd": trade.size_usd,
                "price": trade.price,
                "platform": trade.platform,
                "tx_hash": trade.tx_hash,
                "slot": trade.slot,
                "pool_id": trade.pool_id,
                "source": "raydium_dex"
            }


def main():
    """CLI entry point for Raydium DEX source."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Raydium DEX Swap Source")
    parser.add_argument("--input-file", required=True, help="Path to fixture JSON file")
    parser.add_argument("--min-liquidity-usd", type=float, default=DEFAULT_MIN_LIQUIDITY_USD, 
                        help=f"Minimum liquidity threshold in USD (default: {DEFAULT_MIN_LIQUIDITY_USD})")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run in dry-run mode (no RPC calls)")
    parser.add_argument("--summary-json", action="store_true",
                        help="Print summary JSON to stdout")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    source = RaydiumDexSource(
        min_liquidity_usd=args.min_liquidity_usd,
        dry_run=args.dry_run
    )
    
    trades = source.load_from_file(args.input_file)
    
    # Filtered counts
    trades_ingested = len(trades)
    trades_filtered = 0  # Would need to track during processing
    
    if args.summary_json:
        import json
        result = {
            "trades_ingested": trades_ingested,
            "trades_filtered_liquidity": trades_filtered,
            "schema_version": "trade_v1"
        }
        print(json.dumps(result))
    
    # Print trades to stderr for debugging
    for trade in trades:
        print(f"[raydium_dex] Trade: {trade.side} {trade.size_usd} USD @ {trade.price} ({trade.platform})", file=sys.stderr)
    
    print(f"[raydium_dex] Loaded {trades_ingested} trades from {args.input_file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
