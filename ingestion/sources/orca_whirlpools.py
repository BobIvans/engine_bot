#!/usr/bin/env python3
"""
ingestion/sources/orca_whirlpools.py

Orca Whirlpools Adapter - Decodes Orca Whirlpool concentrated liquidity pools
via RPC or fixture, calculates slippage using simplified CLM model.

PR-ORC.1
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from strategy.amm_math import estimate_whirlpool_slippage_bps

logger = logging.getLogger(__name__)

# Orca Whirlpools program ID
ORCA_WHIRLPOOLS_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"

# Default RPC endpoint
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


def load_fixture(fixture_path: Optional[str] = None) -> Dict[str, Any]:
    """Load fixture data from JSON file."""
    if fixture_path is None:
        fixture_path = Path(__file__).parent.parent / "fixtures" / "execution" / "orca_pool_sample.json"
    
    with open(fixture_path) as f:
        return json.load(f)


class OrcaWhirlpoolDecoder:
    """
    Decoder for Orca Whirlpool concentrated liquidity pools.
    
    PR-ORC.1
    """
    
    def __init__(self):
        """Initialize decoder."""
        pass
    
    def load_from_file(
        self,
        fixture_path: str,
        token_mint: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load pool from fixture file and find matching pool by token mint.
        
        Args:
            fixture_path: Path to fixture JSON file
            token_mint: Token mint to search for (matches mint_y)
            
        Returns:
            Pool data dict or None if not found
        """
        pools = load_fixture(fixture_path)
        
        for pool in pools:
            if pool.get("mint_y") == token_mint:
                logger.debug(f"[orca_whirlpools] Found pool {pool['pool_address'][:16]}... for token {token_mint[:8]}...")
                return pool
        
        logger.warning(f"[orca_whirlpools] No pool found for token {token_mint}")
        return None
    
    async def fetch_from_rpc(
        self,
        token_mint: str,
        rpc_url: str = DEFAULT_RPC_URL,
        allow_orca_whirlpools: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch pool from Solana RPC.
        
        Args:
            token_mint: Token mint to search for
            rpc_url: Solana RPC endpoint URL
            allow_orca_whirlpools: Whether to allow RPC calls
            
        Returns:
            Pool data dict or None if disabled/not found
        """
        if not allow_orca_whirlpools:
            logger.debug("[orca_whirlpools] RPC mode disabled (--allow-orca-whirlpools not set)")
            return None
        
        try:
            import httpx
        except ImportError:
            logger.warning("[orca_whirlpools] httpx not installed, skipping RPC fetch")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for pools using getProgramAccounts
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getProgramAccounts",
                    "params": [
                        ORCA_WHIRLPOOLS_PROGRAM,
                        {
                            "filters": [
                                {"memcmp": {"offset": 72, "bytes": token_mint}}  # mint_y offset
                            ],
                            "encoding": "base64"
                        }
                    ]
                }
                
                response = await client.post(rpc_url, json=payload)
                response.raise_for_status()
                result = response.json()
                
                if "error" in result:
                    logger.error(f"[orca_whirlpools] RPC error: {result['error']}")
                    return None
                
                accounts = result.get("result", [])
                
                if not accounts:
                    logger.warning(f"[orca_whirlpools] No pools found for token {token_mint}")
                    return None
                
                # Decode first matching account
                data = accounts[0]["account"]["data"][0]
                import base64
                raw_data = base64.b64decode(data)
                
                pool = self._decode_pool_data(accounts[0]["pubkey"], raw_data)
                logger.info(f"[orca_whirlpools] Fetched pool {pool['pool_address'][:16]}... via RPC")
                return pool
                
        except Exception as e:
            logger.error(f"[orca_whirlpools] RPC error: {e}")
            return None
    
    def _decode_pool_data(self, pool_address: str, data: bytes) -> Dict[str, Any]:
        """
        Decode raw Whirlpool account data.
        
        Orca Whirlpool layout (approximate):
        - offset 8: sqrt_price_x64 (8 bytes, u64 BE)
        - offset 40: tick_current (4 bytes, i32 BE)
        - offset 48: liquidity (16 bytes, u128 BE)
        - offset 88: fee_tier (4 bytes, u32)
        - mint_x at offset 32 (32 bytes)
        - mint_y at offset 64 (32 bytes)
        """
        import base58
        
        # Parse key fields (simplified - real implementation needs full layout)
        sqrt_price_x64 = int.from_bytes(data[8:16], "big")
        tick_current = int.from_bytes(data[40:44], "big", signed=True)
        liquidity = int.from_bytes(data[48:64], "big")
        
        # Extract mints (32 bytes each at fixed offsets)
        mint_x = base58.b58encode(data[32:64]).decode("utf-8")
        mint_y = base58.b58encode(data[64:96]).decode("utf-8")
        
        # Fee tier (default to 25 bps)
        fee_tier_bps = 25
        if len(data) > 88:
            fee_tier_bps = int.from_bytes(data[88:92], "big")
        
        return {
            "pool_address": pool_address,
            "mint_x": mint_x,
            "mint_y": mint_y,
            "sqrt_price_x64": str(sqrt_price_x64),
            "tick_current": tick_current,
            "liquidity": str(liquidity),
            "tick_spacing": 64,  # Default, would need full decode for actual
            "fee_tier_bps": fee_tier_bps,
        }
    
    def estimate_slippage_for_token(
        self,
        pool: Dict[str, Any],
        size_usd: float,
        token_price_usd: float,
        sol_price_usd: float = 100.0,
    ) -> int:
        """
        Estimate slippage for a token purchase.
        
        Args:
            pool: Pool data dict
            size_usd: Purchase size in USD
            token_price_usd: Token price in USD
            sol_price_usd: SOL price in USD
            
        Returns:
            Estimated slippage in basis points
        """
        liquidity = int(pool["liquidity"])
        sqrt_price_x64 = int(pool["sqrt_price_x64"])
        tick_spacing = pool["tick_spacing"]
        
        slippage = estimate_whirlpool_slippage_bps(
            liquidity=liquidity,
            sqrt_price_x64=sqrt_price_x64,
            tick_spacing=tick_spacing,
            size_usd=size_usd,
            token_price_usd=token_price_usd,
            sol_price_usd=sol_price_usd,
        )
        
        logger.debug(
            f"[orca_whirlpools] slippage for ${size_usd} buy: {slippage} bps "
            f"(liquidity={liquidity}, tick_spacing={tick_spacing})"
        )
        
        return slippage


async def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Orca Whirlpools Decoder")
    parser.add_argument("--input-file", default="fixtures/execution/orca_pool_sample.json",
                       help="Path to fixture file")
    parser.add_argument("--token-mint", required=True, help="Token mint to find")
    parser.add_argument("--size-usd", type=float, default=5000, help="Trade size in USD")
    parser.add_argument("--token-price-usd", type=float, default=0.8, help="Token price in USD")
    parser.add_argument("--allow-orca-whirlpools", action="store_true",
                       help="Allow RPC calls (default: disabled)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--summary-json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    
    decoder = OrcaWhirlpoolDecoder()
    
    # Load from fixture
    pool = decoder.load_from_file(args.input_file, args.token_mint)
    
    if pool is None:
        logger.error(f"[orca_whirlpools] Pool not found for {args.token_mint}")
        return 1
    
    # Estimate slippage
    slippage = decoder.estimate_slippage_for_token(
        pool=pool,
        size_usd=args.size_usd,
        token_price_usd=args.token_price_usd,
    )
    
    logger.info(f"[orca_whirlpools] decoded pool {pool['pool_address'][:16]}...")
    logger.info(f"[orca_whirlpools] tick={pool['tick_current']}, liquidity={pool['liquidity']}")
    logger.info(f"[orca_whirlpools] estimated slippage for ${args.size_usd} buy: {slippage} bps")
    
    if args.summary_json and not args.dry_run:
        output = {
            "pool_decoded": True,
            "pool_address": pool["pool_address"],
            "tick_current": pool["tick_current"],
            "liquidity": pool["liquidity"],
            "estimated_slippage_bps": slippage,
            "schema_version": "orca_pool.v1",
        }
        print(json.dumps(output))
    
    return 0


if __name__ == "__main__":
    import asyncio
    exit(asyncio.run(main()))
