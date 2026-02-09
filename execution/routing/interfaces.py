"""
execution/routing/interfaces.py

Abstract interfaces for liquidity sources.

PR-U.4
"""
from abc import ABC, abstractmethod
from typing import Optional
from execution.routing.types import SimulatedQuote


class LiquiditySource(ABC):
    """
    Abstract base class for liquidity sources.
    
    All DEX adapters and API clients must implement this interface
    to be registered with the LiquidityRouter.
    
    PR-U.4
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return the source identifier name.
        
        Returns:
            Unique name for this source (e.g., "raydium_v4", "jupiter_api")
        """
        pass
    
    @abstractmethod
    def get_quote(
        self,
        mint_in: str,
        mint_out: str,
        amount_in: int,
    ) -> Optional[SimulatedQuote]:
        """
        Get a quote for swapping amount_in of mint_in to mint_out.
        
        Args:
            mint_in: Input token mint address (base58)
            mint_out: Output token mint address (base58)
            amount_in: Input amount in atomic units
            
        Returns:
            SimulatedQuote if successful, None if quote unavailable
        """
        pass
    
    def is_available(self) -> bool:
        """
        Check if the source is currently available.
        
        Default implementation returns True. Override for health checks.
        
        Returns:
            True if source is operational
        """
        return True
