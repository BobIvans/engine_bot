"""
ingestion/dex/raydium/decoder.py

Raydium Pool Decoder - High-level interface for pool data decoding.

PR-U.1
"""
import logging
from typing import Any, Dict, Optional

from .layouts import (
    PoolState,
    VaultState,
    decode_pool_state,
    decode_vault_state,
    guess_encoding_and_decode,
)

logger = logging.getLogger(__name__)


class RaydiumDecoder:
    """
    High-level decoder for Raydium pool data.
    
    PR-U.1
    """
    
    def __init__(self):
        """Initialize decoder."""
        pass
    
    def decode_pool(self, data: bytes) -> PoolState:
        """
        Decode pool state from raw bytes.
        
        Args:
            data: Raw account data (bytes)
            
        Returns:
            PoolState object
        """
        try:
            pool = decode_pool_state(data)
            logger.debug(f"[raydium] Decoded pool: {pool.coin_mint[:8]}...{pool.pc_mint[:8]}...")
            return pool
        except ValueError as e:
            logger.error(f"[raydium] Failed to decode pool: {e}")
            raise
    
    def decode_pool_from_string(self, data: str) -> PoolState:
        """
        Decode pool from base64 or hex string.
        
        Args:
            data: Encoded string
            
        Returns:
            PoolState object
        """
        return guess_encoding_and_decode(data)
    
    def decode_vault(self, data: bytes) -> VaultState:
        """
        Decode vault state from raw bytes.
        
        Args:
            data: Raw vault account data
            
        Returns:
            VaultState object
        """
        try:
            vault = decode_vault_state(data)
            return vault
        except ValueError as e:
            logger.error(f"[raydium] Failed to decode vault: {e}")
            raise
    
    def get_pool_info(self, pool: PoolState) -> Dict[str, Any]:
        """
        Get human-readable pool info.
        
        Args:
            pool: Decoded PoolState
            
        Returns:
            Dict with pool information
        """
        return {
            "status": pool.get_status_string(),
            "is_tradable": pool.is_opened,
            "coin_mint": pool.coin_mint,
            "pc_mint": pool.pc_mint,
            "lp_mint": pool.lp_mint,
            "coin_decimals": pool.coin_decimals,
            "pc_decimals": pool.pc_decimals,
            "authority": pool.authority,
            "market": pool.market,
            "vaults": {
                "coin": pool.coin_vault,
                "pc": pool.pc_vault,
            },
        }
    
    def validate_pool(self, pool: PoolState) -> bool:
        """
        Validate pool state.
        
        Args:
            pool: Decoded PoolState
            
        Returns:
            True if pool is valid for trading
        """
        if not pool.is_opened:
            logger.warning(f"[raydium] Pool is not open for trading: {pool.get_status_string()}")
            return False
        
        if pool.coin_decimals <= 0 or pool.pc_decimals <= 0:
            logger.warning("[raydium] Invalid decimals")
            return False
        
        return True
    
    def extract_pubkeys(self, pool: PoolState) -> Dict[str, str]:
        """
        Extract all pubkeys from pool for RPC queries.
        
        Args:
            pool: Decoded PoolState
            
        Returns:
            Dict mapping key names to pubkey strings
        """
        return {
            "amm_authority": pool.authority,
            "amm_coin_vault": pool.coin_vault,
            "amm_pc_vault": pool.pc_vault,
            "open_orders": pool.open_orders,
            "target_orders": pool.target_orders,
            "market": pool.market,
            "market_program": pool.market_program,
            "lp_mint": pool.lp_mint,
            "coin_mint": pool.coin_mint,
            "pc_mint": pool.pc_mint,
        }


def decode_raydium_pool(data: bytes) -> PoolState:
    """
    Convenience function to decode Raydium pool.
    
    Args:
        data: Raw account data
        
    Returns:
        PoolState object
    """
    decoder = RaydiumDecoder()
    return decoder.decode_pool(data)


def decode_raydium_pool_str(data: str) -> PoolState:
    """
    Convenience function to decode Raydium pool from string.
    
    Args:
        data: Base64 or hex encoded string
        
    Returns:
        PoolState object
    """
    decoder = RaydiumDecoder()
    return decoder.decode_pool_from_string(data)
