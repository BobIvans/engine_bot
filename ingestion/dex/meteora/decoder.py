"""
ingestion/dex/meteora/decoder.py

Meteora DLMM Decoder - High-level interface for LbPair data decoding.

PR-U.3
"""
import logging
from typing import Any, Dict, Optional

from .layouts import (
    LbPairState,
    decode_lb_pair,
    guess_encoding_and_decode,
)

logger = logging.getLogger(__name__)


class MeteoraDecoder:
    """
    High-level decoder for Meteora DLMM LbPair data.
    
    PR-U.3
    """
    
    def __init__(self):
        """Initialize decoder."""
        pass
    
    def decode_lb_pair(self, data: bytes) -> LbPairState:
        """
        Decode LbPair state from raw bytes.
        
        Args:
            data: Raw account data (bytes)
            
        Returns:
            LbPairState object
        """
        try:
            pool = decode_lb_pair(data)
            logger.debug(
                f"[meteora] Decoded pool: {pool.token_x_mint[:8]}.../{pool.token_y_mint[:8]}... "
                f"BinStep={pool.bin_step} ActiveID={pool.active_id} Price={self._calc_price(pool)}"
            )
            return pool
        except ValueError as e:
            logger.error(f"[meteora] Failed to decode pool: {e}")
            raise
    
    def decode_from_string(self, data: str) -> LbPairState:
        """
        Decode LbPair from base64 or hex string.
        
        Args:
            data: Encoded string
            
        Returns:
            LbPairState object
        """
        return guess_encoding_and_decode(data)
    
    def get_pool_info(self, pool: LbPairState) -> Dict[str, Any]:
        """
        Get human-readable pool info.
        
        Args:
            pool: Decoded LbPairState
            
        Returns:
            Dict with pool information
        """
        price = self._calc_price(pool)
        
        return {
            "token_x_mint": pool.token_x_mint,
            "token_y_mint": pool.token_y_mint,
            "token_x_vault": pool.token_x_vault,
            "token_y_vault": pool.token_y_vault,
            "bin_step": pool.bin_step,
            "base_factor": pool.base_factor,
            "active_id": pool.active_id,
            "current_price": price,
            "token_x_decimals": pool.token_x_decimals,
            "token_y_decimals": pool.token_y_decimals,
            "is_initialized": pool.is_initialized,
        }
    
    def validate_pool(self, pool: LbPairState) -> bool:
        """
        Validate pool state.
        
        Args:
            pool: Decoded LbPairState
            
        Returns:
            True if pool is valid
        """
        if pool.active_id == 0:
            logger.warning("[meteora] Pool active_id is 0 (uninitialized)")
            return False
        
        if pool.bin_step <= 0:
            logger.warning("[meteora] Invalid bin_step")
            return False
        
        return True
    
    def _calc_price(self, pool: LbPairState) -> float:
        """
        Calculate current price from pool state.
        
        Args:
            pool: Decoded LbPairState
            
        Returns:
            Current price
        """
        from .math import MeteoraMath
        
        return MeteoraMath.get_price_from_id(
            pool.active_id,
            pool.bin_step,
            pool.token_x_decimals,
            pool.token_y_decimals,
        )
    
    def get_price_info(self, pool: LbPairState) -> Dict[str, Any]:
        """
        Get detailed price information.
        
        Args:
            pool: Decoded LbPairState
            
        Returns:
            Dict with price details
        """
        from .math import MeteoraMath
        
        current_price = MeteoraMath.get_price_from_id(
            pool.active_id,
            pool.bin_step,
            pool.token_x_decimals,
            pool.token_y_decimals,
        )
        
        # Get price range for current bin
        lower_price = MeteoraMath.get_price_from_id(
            pool.active_id - 1,
            pool.bin_step,
            pool.token_x_decimals,
            pool.token_y_decimals,
        )
        upper_price = MeteoraMath.get_price_from_id(
            pool.active_id + 1,
            pool.bin_step,
            pool.token_x_decimals,
            pool.token_y_decimals,
        )
        
        return {
            "current_price": current_price,
            "active_id": pool.active_id,
            "bin_step": pool.bin_step,
            "lower_bin_price": lower_price,
            "upper_bin_price": upper_price,
            "price_range": upper_price - lower_price,
            "decimals_x": pool.token_x_decimals,
            "decimals_y": pool.token_y_decimals,
        }


def decode_meteora_lb_pair(data: bytes) -> LbPairState:
    """
    Convenience function to decode Meteora LbPair.
    
    Args:
        data: Raw account data
        
    Returns:
        LbPairState object
    """
    decoder = MeteoraDecoder()
    return decoder.decode_lb_pair(data)


def decode_meteora_lb_pair_str(data: str) -> LbPairState:
    """
    Convenience function to decode Meteora LbPair from string.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        LbPairState object
    """
    decoder = MeteoraDecoder()
    return decoder.decode_from_string(data)
