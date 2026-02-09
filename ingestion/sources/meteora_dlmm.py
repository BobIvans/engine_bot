#!/usr/bin/env python3
"""
ingestion/sources/meteora_dlmm.py

Meteora DLMM Pool Decoder Adapter - Fetches pool state from Raydium DLMM pools
via RPC or fixture, decodes bin-based liquidity parameters, and estimates slippage.

PR-MET.1

Features:
- Bin-based liquidity model (discrete price intervals)
- Simplified slippage estimation based on active bin liquidity
- Supports both fixture (deterministic) and RPC (real-time) modes
- Graceful degradation on RPC errors
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from strategy.amm_math import estimate_dlmm_slippage_bps

logger = logging.getLogger(__name__)

# Meteora DLMM program ID
METEORA_DLMM_PROGRAM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccj5HBQVXMCmTrxASL"

# SOL mint address
SOL_MINT = "So11111111111111111111111111111111111111112"

# Default parameters
DEFAULT_MIN_LIQUIDITY = 1000  # Minimum active bin liquidity for valid pool


@dataclass
class MeteoraPool:
    """Meteora DLMM pool state."""
    pool_address: str
    mint_x: str  # Usually SOL
    mint_y: str  # The token being traded
    current_bin_id: int
    bin_step_bps: int  # Bin step in basis points (1 = 0.01%)
    active_bin_liquidity: int  # Liquidity in active bins (±3 from current)
    fee_tier_bps: int  # Protocol fee in bps
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pool_address": self.pool_address,
            "mint_x": self.mint_x,
            "mint_y": self.mint_y,
            "current_bin_id": self.current_bin_id,
            "bin_step_bps": self.bin_step_bps,
            "active_bin_liquidity": str(self.active_bin_liquidity),
            "fee_tier_bps": self.fee_tier_bps
        }


@dataclass
class SlippageResult:
    """Slippage estimation result."""
    pool_address: str
    current_bin_id: int
    bin_step_bps: int
    active_bin_liquidity: int
    size_usd: float
    token_price_usd: float
    effective_depth_usd: float
    slippage_bps: int
    schema_version: str = "meteora_pool.v1"


class MeteoraPoolDecoder:
    """
    Decoder for Meteora DLMM pools.
    
    Supports:
    - Fixture mode: Load from JSON file with pre-decoded pools
    - RPC mode: Fetch real pool state via Solana RPC (optional)
    """
    
    def __init__(
        self,
        min_liquidity: int = DEFAULT_MIN_LIQUIDITY,
        dry_run: bool = True
    ):
        """
        Initialize Meteora DLMM decoder.
        
        Args:
            min_liquidity: Minimum active bin liquidity for valid pool
            dry_run: If True, only process fixtures without RPC calls
        """
        self.min_liquidity = min_liquidity
        self.dry_run = dry_run
    
    def load_from_file(
        self,
        path: str,
        token_mint: str
    ) -> Optional[MeteoraPool]:
        """
        Load and decode pool from fixture file.
        
        Args:
            path: Path to JSON fixture file
            token_mint: Mint address to search for (matches mint_y)
            
        Returns:
            MeteoraPool or None if not found or invalid
        """
        fixture_path = Path(path)
        if not fixture_path.exists():
            logger.error(f"Fixture file not found: {path}")
            return None
        
        with open(fixture_path) as f:
            fixtures = json.load(f)
        
        for fixture in fixtures:
            pool = self._fixture_to_pool(fixture)
            if pool is not None and pool.mint_y.lower() == token_mint.lower():
                return pool
        
        logger.debug(f"Pool not found for token mint: {token_mint}")
        return None
    
    def _fixture_to_pool(self, fixture: Dict[str, Any]) -> Optional[MeteoraPool]:
        """
        Convert fixture dict to MeteoraPool.
        
        Args:
            fixture: Fixture dict
            
        Returns:
            MeteoraPool or None if invalid
        """
        try:
            pool_address = fixture.get("pool_address", "")
            mint_x = fixture.get("mint_x", "")
            mint_y = fixture.get("mint_y", "")
            current_bin_id = fixture.get("current_bin_id", 0)
            bin_step_bps = fixture.get("bin_step_bps", 0)
            active_bin_liquidity_raw = fixture.get("active_bin_liquidity", "0")
            fee_tier_bps = fixture.get("fee_tier_bps", 0)
            
            # Parse active_bin_liquidity
            if isinstance(active_bin_liquidity_raw, (int, float)):
                active_bin_liquidity = int(active_bin_liquidity_raw)
            elif isinstance(active_bin_liquidity_raw, str):
                active_bin_liquidity = int(active_bin_liquidity_raw) if active_bin_liquidity_raw else 0
            else:
                active_bin_liquidity = 0
            
            # Validate required fields
            if not pool_address or not mint_x or not mint_y:
                logger.warning(f"Invalid pool fixture: missing required fields")
                return None
            
            # Skip empty pools
            if active_bin_liquidity <= 0:
                logger.debug(f"Pool {pool_address} has zero active liquidity")
                return None
            
            return MeteoraPool(
                pool_address=pool_address,
                mint_x=mint_x,
                mint_y=mint_y,
                current_bin_id=current_bin_id,
                bin_step_bps=bin_step_bps,
                active_bin_liquidity=active_bin_liquidity,
                fee_tier_bps=fee_tier_bps
            )
        except Exception as e:
            logger.warning(f"Failed to parse pool fixture: {e}")
            return None
    
    def fetch_from_rpc(
        self,
        token_mint: str,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        allow_meteora_dlmm: bool = False
    ) -> Optional[MeteoraPool]:
        """
        Fetch real pool state from Meteora DLMM via RPC.
        
        This method is only called when --allow-meteora-dlmm flag is set.
        
        Args:
            token_mint: Mint address to search for
            rpc_url: Solana RPC endpoint URL
            allow_meteora_dlmm: Whether to allow RPC fetching
            
        Returns:
            MeteoraPool or None if not found or error
        """
        if not allow_meteora_dlmm or self.dry_run:
            logger.debug("Meteora DLMM RPC fetching disabled or dry-run mode")
            return None
        
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available, skipping RPC fetch")
            return None
        
        try:
            client = httpx.AsyncClient(timeout=30.0)
        except Exception as e:
            logger.warning(f"Failed to create RPC client: {e}")
            return None
        
        try:
            # Search for pools using getProgramAccounts
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    METEORA_DLMM_PROGRAM_ID,
                    {
                        "filters": [
                            {"dataSize": 300},  # Approximate account size
                            {
                                "memcmp": {
                                    "offset": 8,  # Skip discriminator
                                    "bytes": token_mint[:32]  # mint_y comparison (simplified)
                                }
                            }
                        ]
                    }
                ]
            }
            
            response = client.post(rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "result" not in data or not data["result"]:
                logger.debug(f"No Meteora DLMM pools found for token: {token_mint}")
                return None
            
            # Decode first matching account (simplified)
            # In production, would need proper Borsh deserialization
            for account in data["result"][:1]:  # Just take first match
                pubkey = account.get("pubkey", "")
                data_b64 = account.get("account", {}).get("data", "")
                
                pool = self._decode_account(pubkey, data_b64, token_mint)
                if pool is not None:
                    return pool
            
            return None
            
        except Exception as e:
            logger.warning(f"Meteora DLMM RPC error: {e}")
            return None
    
    def _decode_account(
        self,
        pubkey: str,
        data_b64: str,
        token_mint: str
    ) -> Optional[MeteoraPool]:
        """
        Decode raw account data into MeteoraPool.
        
        This is a simplified decoder. In production, would use proper Borsh schema.
        
        Args:
            pubkey: Pool account public key
            data_b64: Base64-encoded account data
            token_mint: Expected token mint (mint_y)
            
        Returns:
            MeteoraPool or None if decoding fails
        """
        import base64
        
        try:
            data = base64.b64decode(data_b64)
            
            # Simplified offsets (actual offsets may vary by version)
            # offset 8: discriminator (8 bytes)
            # offset 16: current_bin_id (8 bytes, i64)
            # offset 24: bin_step_bps (4 bytes, u32)
            # offset 32: active_bin_liquidity (8 bytes, u64)
            # offset 48: fee_tier_bps (4 bytes, u32)
            # offset 64+: mint addresses (32 bytes each)
            
            if len(data) < 96:
                logger.warning(f"Account data too short: {len(data)} bytes")
                return None
            
            import struct
            current_bin_id = struct.unpack("<q", data[16:24])[0]
            bin_step_bps = struct.unpack("<I", data[24:28])[0]
            active_bin_liquidity = struct.unpack("<Q", data[32:40])[0]
            fee_tier_bps = struct.unpack("<I", data[48:52])[0]
            
            # Extract mints (simplified)
            mint_x = data[64:96].decode('utf-8', errors='ignore').strip('\x00')
            mint_y = data[96:128].decode('utf-8', errors='ignore').strip('\x00')
            
            if mint_y.lower() != token_mint.lower():
                return None
            
            return MeteoraPool(
                pool_address=pubkey,
                mint_x=mint_x,
                mint_y=mint_y,
                current_bin_id=current_bin_id,
                bin_step_bps=bin_step_bps,
                active_bin_liquidity=active_bin_liquidity,
                fee_tier_bps=fee_tier_bps
            )
        except Exception as e:
            logger.warning(f"Failed to decode account: {e}")
            return None
    
    def estimate_slippage(
        self,
        pool: MeteoraPool,
        size_usd: float,
        token_price_usd: float
    ) -> SlippageResult:
        """
        Estimate slippage for a given trade size.
        
        Args:
            pool: Meteora DLMM pool
            size_usd: Trade size in USD
            token_price_usd: Current token price in USD
            
        Returns:
            SlippageResult with estimation details
        """
        # Calculate effective depth for logging
        bin_density_factor = min(5.0, 100.0 / max(1, pool.bin_step_bps))
        effective_token_amount = pool.active_bin_liquidity / 1e6
        effective_depth_usd = effective_token_amount * token_price_usd * bin_density_factor
        
        # Calculate slippage using pure math function
        slippage_bps = estimate_dlmm_slippage_bps(
            active_bin_liquidity=pool.active_bin_liquidity,
            bin_step_bps=pool.bin_step_bps,
            size_usd=size_usd,
            token_price_usd=token_price_usd
        )
        
        return SlippageResult(
            pool_address=pool.pool_address,
            current_bin_id=pool.current_bin_id,
            bin_step_bps=pool.bin_step_bps,
            active_bin_liquidity=pool.active_bin_liquidity,
            size_usd=size_usd,
            token_price_usd=token_price_usd,
            effective_depth_usd=effective_depth_usd,
            slippage_bps=slippage_bps
        )


def main():
    """CLI entry point for Meteora DLMM decoder."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Meteora DLMM Pool Decoder")
    parser.add_argument("--input-file", required=True, help="Path to fixture JSON file")
    parser.add_argument("--token-mint", required=True, help="Token mint address to search for")
    parser.add_argument("--size-usd", type=float, default=3000.0, help="Trade size in USD")
    parser.add_argument("--token-price-usd", type=float, required=True, help="Token price in USD")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run in dry-run mode (no RPC calls)")
    parser.add_argument("--summary-json", action="store_true",
                        help="Print summary JSON to stdout")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    decoder = MeteoraPoolDecoder(dry_run=args.dry_run)
    
    # Load pool from fixture
    pool = decoder.load_from_file(args.input_file, args.token_mint)
    
    if pool is None:
        print("[meteora_dlmm] Pool not found in fixture", file=sys.stderr)
        if args.summary_json:
            print(json.dumps({"pool_decoded": False}))
        return 1
    
    # Estimate slippage
    result = decoder.estimate_slippage(pool, args.size_usd, args.token_price_usd)
    
    # Output to stderr
    print(f"[meteora_dlmm] decoded pool {pool.pool_address[:8]}...: bin={pool.current_bin_id}, step={pool.bin_step_bps}bps, liquidity={pool.active_bin_liquidity/1e6:.0f}M", file=sys.stderr)
    print(f"[meteora_dlmm] estimated slippage for ${args.size_usd} buy: {result.slippage_bps} bps (effective depth=${result.effective_depth_usd:.0f})", file=sys.stderr)
    
    # Summary JSON to stdout
    if args.summary_json:
        summary = {
            "pool_decoded": True,
            "pool_address": pool.pool_address,
            "current_bin_id": pool.current_bin_id,
            "bin_step_bps": pool.bin_step_bps,
            "active_bin_liquidity": pool.active_bin_liquidity,
            "estimated_slippage_bps": result.slippage_bps,
            "effective_depth_usd": round(result.effective_depth_usd, 2),
            "schema_version": "meteora_pool.v1"
        }
        print(json.dumps(summary))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
