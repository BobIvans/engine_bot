#!/usr/bin/env python3
"""
ingestion/sources/raydium_pool.py

Raydium Pool Decoder Adapter - Fetches pool state via RPC or fixture,
decodes reserves, and calculates slippage via XYK model.

PR-JU.2
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from strategy.amm_math import estimate_slippage_bps

logger = logging.getLogger(__name__)

# Default RPC endpoint
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"

# Pool cache TTL in seconds
CACHE_TTL = 30


def load_fixture(fixture_path: Optional[str] = None) -> Dict[str, Any]:
    """Load fixture data from JSON file."""
    if fixture_path is None:
        fixture_path = Path(__file__).parent.parent / "fixtures" / "execution" / "raydium_pool_sample.json"
    
    with open(fixture_path) as f:
        return json.load(f)


async def fetch_pool_via_rpc(
    pool_address: str,
    rpc_url: str = DEFAULT_RPC_URL,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fetch pool state via Solana RPC.
    
    Args:
        pool_address: Pubkey of the Raydium pool
        rpc_url: Solana RPC endpoint URL
        client: Optional HTTPX client for connection reuse
        
    Returns:
        Dict with decoded pool state
        
    Raises:
        ValueError: If RPC fails or pool not found
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for RPC mode. Install with: pip install httpx")
    
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
        close_client = True
    
    try:
        # RPC request for account data
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [
                pool_address,
                {
                    "encoding": "base64",
                    "dataSlice": {
                        "offset": 0,
                        "length": 0  # Full account
                    }
                }
            ]
        }
        
        response = await client.post(rpc_url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            raise ValueError(f"RPC error: {result['error']}")
        
        if "result" not in result or result["result"] is None:
            raise ValueError(f"Pool not found: {pool_address}")
        
        # Extract base64 data
        data = result["result"]["value"]["data"][0]
        
        # Decode using Raydium layout
        from ingestion.dex.raydium.decoder import decode_raydium_pool_str
        pool = decode_raydium_pool_str(data)
        
        # Also fetch vault balances
        vault_data = await fetch_vault_balances(
            pool.coin_vault, pool.pc_vault, rpc_url, client
        )
        
        return {
            "pool_address": pool_address,
            "mint_x": pool.coin_mint,
            "mint_y": pool.pc_mint,
            "reserve_x": str(vault_data["coin_amount"]),
            "reserve_y": str(vault_data["pc_amount"]),
            "lp_supply": "0",  # Would need separate query
            "fee_tier_bps": 25,  # Raydium standard fee
            "decimals_x": pool.coin_decimals,
            "decimals_y": pool.pc_decimals,
        }
        
    finally:
        if close_client:
            await client.aclose()


async def fetch_vault_balances(
    coin_vault: str,
    pc_vault: str,
    rpc_url: str,
    client: Any,
) -> Dict[str, int]:
    """Fetch vault token balances via RPC."""
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for RPC mode")
    
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "getMultipleAccounts",
        "params": [
            [coin_vault, pc_vault],
            {
                "encoding": "base64",
                "dataSlice": {
                    "offset": 64,  # Skip mint + owner (32+32)
                    "length": 8    # Amount field
                }
            }
        ]
    }
    
    response = await client.post(rpc_url, json=payload)
    response.raise_for_status()
    result = response.json()
    
    if "error" in result:
        raise ValueError(f"Vault fetch error: {result['error']}")
    
    balances = {}
    for i, (vault_name, vault_addr) in enumerate([("coin", coin_vault), ("pc", pc_vault)]):
        try:
            data = result["result"]["value"][i]["data"][0]
            import base64
            amount = int.from_bytes(base64.b64decode(data), "little")
            balances[f"{vault_name}_amount"] = amount
        except (KeyError, TypeError, ValueError):
            balances[f"{vault_name}_amount"] = 0
    
    return balances


async def get_pool_for_swap(
    input_mint: str,
    output_mint: str,
    amount_in: int,
    use_fixture: bool = True,
    fixture_path: Optional[str] = None,
    rpc_url: str = DEFAULT_RPC_URL,
) -> Dict[str, Any]:
    """
    Get pool data for a specific swap and calculate slippage.
    
    Args:
        input_mint: Mint address of input token
        output_mint: Mint address of output token
        amount_in: Amount of input token (in lamports/base units)
        use_fixture: If True, use fixture instead of RPC
        fixture_path: Optional path to fixture file
        rpc_url: RPC URL for live fetching
        
    Returns:
        Dict with pool info and estimated slippage
    """
    if use_fixture:
        pools = load_fixture(fixture_path)
        # Find matching pool
        for pool in pools:
            if (pool["mint_x"] == input_mint and pool["mint_y"] == output_mint) or \
               (pool["mint_x"] == output_mint and pool["mint_y"] == input_mint):
                
                # Calculate slippage
                is_input_x = pool["mint_x"] == input_mint
                reserve_in = float(pool["reserve_x"]) if is_input_x else float(pool["reserve_y"])
                reserve_out = float(pool["reserve_y"]) if is_input_x else float(pool["reserve_x"])
                
                slippage_bps = estimate_slippage_bps(
                    pool_address=pool["pool_address"],
                    amount_in=amount_in,
                    token_mint=input_mint,
                    reserve_in=reserve_in,
                    reserve_out=reserve_out,
                    fee_bps=pool["fee_tier_bps"],
                )
                
                return {
                    "pool": pool,
                    "estimated_slippage_bps": slippage_bps,
                    "source": "fixture",
                }
        
        raise ValueError(f"No pool found for {input_mint}/{output_mint} in fixture")
    
    # Live RPC fetch would require finding the right pool address first
    # This is a simplified version - in production you'd query Raydium's program
    raise NotImplementedError("Live pool discovery requires Raydium program indexing")


def estimate_slippage_for_trade(
    pool_data: Dict[str, Any],
    amount_in: int,
    input_mint: str,
) -> int:
    """
    Estimate slippage in basis points for a trade.
    
    Args:
        pool_data: Pool data dict
        amount_in: Amount of input token
        input_mint: Mint of input token
        
    Returns:
        Estimated slippage in basis points (int)
    """
    is_input_x = pool_data["mint_x"] == input_mint
    reserve_in = float(pool_data["reserve_x"]) if is_input_x else float(pool_data["reserve_y"])
    reserve_out = float(pool_data["reserve_y"]) if is_input_x else float(pool_data["reserve_x"])
    fee_bps = pool_data.get("fee_tier_bps", 25)
    
    return estimate_slippage_bps(
        pool_address=pool_data["pool_address"],
        amount_in=amount_in,
        token_mint=input_mint,
        reserve_in=reserve_in,
        reserve_out=reserve_out,
        fee_bps=fee_bps,
    )


async def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Raydium Pool Decoder")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="Solana RPC URL")
    parser.add_argument("--pool", help="Pool address to query")
    parser.add_argument("--fixture", action="store_true", default=True, help="Use fixture")
    parser.add_argument("--swap", nargs=3, metavar=("INPUT_MINT", "OUTPUT_MINT", "AMOUNT"),
                       help="Simulate swap and show slippage")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    
    if args.swap:
        input_mint, output_mint, amount = args.swap
        result = await get_pool_for_swap(
            input_mint, output_mint, int(amount),
            use_fixture=args.fixture,
            rpc_url=args.rpc_url,
        )
        print(json.dumps(result, indent=2))
    elif args.pool:
        if args.fixture:
            pools = load_fixture()
            for pool in pools:
                if pool["pool_address"] == args.pool:
                    print(json.dumps(pool, indent=2))
                    break
            else:
                print(f"Pool {args.pool} not found in fixture")
        else:
            pool = await fetch_pool_via_rpc(args.pool, args.rpc_url)
            print(json.dumps(pool, indent=2))
    else:
        # Show all fixture pools
        pools = load_fixture()
        print(json.dumps(pools, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
