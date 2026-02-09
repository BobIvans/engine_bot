"""
ingestion/dex/orca/decoder.py

Orca Whirlpools Decoder - High-level interface for Whirlpool data decoding.

PR-U.2
"""
import logging
from typing import Any, Dict, Optional

from .layouts import (
    WhirlpoolState,
    decode_whirlpool,
    guess_encoding_and_decode,
    WHIRLPOOL_DISCRIMINATOR,
)

logger = logging.getLogger(__name__)


class OrcaDecoder:
    """
    High-level decoder for Orca Whirlpool CLMM data.
    
    PR-U.2
    """
    
    # Known token mints
    SOL_MINT = "So11111111111111111111111111111111111111112"  # Wrapped SOL
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
    
    def __init__(self):
        """Initialize decoder."""
        pass
    
    def decode_whirlpool(self, data: bytes) -> WhirlpoolState:
        """
        Decode Whirlpool state from raw bytes.
        
        Args:
            data: Raw account data (bytes)
            
        Returns:
            WhirlpoolState object
        """
        try:
            pool = decode_whirlpool(data)
            logger.debug(
                f"[orca] Decoded pool: {pool.token_mint_a[:8]}.../{pool.token_mint_b[:8]}... "
                f"Tick={pool.tick_current_index} Price={self._calc_price(pool)}"
            )
            return pool
        except ValueError as e:
            logger.error(f"[orca] Failed to decode pool: {e}")
            raise
    
    def decode_from_string(self, data: str) -> WhirlpoolState:
        """
        Decode Whirlpool from base64 or hex string.
        
        Args:
            data: Encoded string
            
        Returns:
            WhirlpoolState object
        """
        return guess_encoding_and_decode(data)
    
    def get_pool_info(self, pool: WhirlpoolState) -> Dict[str, Any]:
        """
        Get human-readable pool info.
        
        Args:
            pool: Decoded WhirlpoolState
            
        Returns:
            Dict with pool information
        """
        price = self._calc_price(pool)
        
        return {
            "token_mint_a": pool.token_mint_a,
            "token_mint_b": pool.token_mint_b,
            "token_vault_a": pool.token_vault_a,
            "token_vault_b": pool.token_vault_b,
            "tick_current_index": pool.tick_current_index,
            "tick_spacing": pool.tick_spacing,
            "sqrt_price": pool.sqrt_price,
            "liquidity": pool.liquidity,
            "token_decimal_a": pool.token_decimal_a,
            "token_decimal_b": pool.token_decimal_b,
            "current_price": price,
            "is_initialized": pool.is_initialized,
        }
    
    def validate_pool(self, pool: WhirlpoolState) -> bool:
        """
        Validate pool state.
        
        Args:
            pool: Decoded WhirlpoolState
            
        Returns:
            True if pool is valid for trading
        """
        if not pool.is_initialized:
            logger.warning("[orca] Pool is not initialized")
            return False
        
        if pool.sqrt_price <= 0:
            logger.warning("[orca] Invalid sqrt_price")
            return False
        
        return True
    
    def is_sol_usdc_pool(self, pool: WhirlpoolState) -> bool:
        """
        Check if this is the SOL/USDC pool.
        
        Args:
            pool: Decoded WhirlpoolState
            
        Returns:
            True if SOL/USDC pool
        """
        return (
            pool.token_mint_a == self.SOL_MINT and pool.token_mint_b == self.USDC_MINT
        ) or (
            pool.token_mint_a == self.USDC_MINT and pool.token_mint_b == self.SOL_MINT
        )
    
    def _calc_price(self, pool: WhirlpoolState) -> float:
        """
        Calculate current price from pool state.
        
        Args:
            pool: Decoded WhirlpoolState
            
        Returns:
            Current price
        """
        from .math import OrcaMath
        
        # Determine which token is which
        if pool.token_mint_a == self.SOL_MINT:
            decimals_a = 9  # SOL
            decimals_b = 6  # USDC
        else:
            decimals_a = 6  # USDC
            decimals_b = 9  # SOL
        
        return OrcaMath.sqrt_price_x64_to_price(
            pool.sqrt_price, decimals_a, decimals_b
        )
    
    def get_price_info(self, pool: WhirlpoolState) -> Dict[str, Any]:
        """
        Get detailed price information.
        
        Args:
            pool: Decoded WhirlpoolState
            
        Returns:
            Dict with price details
        """
        from .math import OrcaMath
        
        # Determine decimals based on mints
        if pool.token_mint_a == self.SOL_MINT:
            decimals_a = 9
            decimals_b = 6
        else:
            decimals_a = 6
            decimals_b = 9
        
        # Current price from sqrt_price
        current_price = OrcaMath.sqrt_price_x64_to_price(
            pool.sqrt_price, decimals_a, decimals_b
        )
        
        # Price from tick index
        tick_price = OrcaMath.tick_to_price(
            pool.tick_current_index, decimals_a, decimals_b
        )
        
        # Liquidity estimate (assuming SOL is ~$150)
        liquidity_usd = OrcaMath.get_liquidity_usd_estimate(
            pool.liquidity, current_price, decimals_a
        )
        
        return {
            "current_price": current_price,
            "tick_price": tick_price,
            "tick_index": pool.tick_current_index,
            "sqrt_price": pool.sqrt_price,
            "liquidity": pool.liquidity,
            "liquidity_usd_estimate": liquidity_usd,
            "decimals_a": decimals_a,
            "decimals_b": decimals_b,
        }


def decode_orca_whirlpool(data: bytes) -> WhirlpoolState:
    """
    Convenience function to decode Orca Whirlpool.
    
    Args:
        data: Raw account data
        
    Returns:
        WhirlpoolState object
    """
    decoder = OrcaDecoder()
    return decoder.decode_whirlpool(data)


def decode_orca_whirlpool_str(data: str) -> WhirlpoolState:
    """
    Convenience function to decode Orca Whirlpool from string.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        WhirlpoolState object
    """
    decoder = OrcaDecoder()
    return decoder.decode_from_string(data)
