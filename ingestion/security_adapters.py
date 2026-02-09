"""ingestion/security_adapters.py

PR-B.3 Security API Adapters.

This module provides adapter interfaces for fetching token security data
from external APIs (GMGN, RugCheck, etc.). Adapters are used in the
ingestion/pipeline layer to enrich TokenSnapshot before strategy evaluation.

Note: The pure strategy layer (strategy/honeypot_filter.py) does NOT call
these adapters - it only reads from the already-enriched TokenSnapshot.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class SecurityAdapter(ABC):
    """Abstract base class for security API adapters.
    
    All adapters must implement fetch_security_info which returns
    a dictionary of security fields for the given token mint.
    """
    
    @abstractmethod
    def fetch_security_info(self, mint: str) -> Dict[str, Any]:
        """Fetch security information for a token.
        
        Args:
            mint: Token mint address
            
        Returns:
            Dictionary containing security fields:
            - is_honeypot: Optional[bool]
            - freeze_authority: Optional[bool]
            - mint_authority: Optional[bool]
            - top_holders_pct: Optional[float]
            - Other provider-specific fields
        """
        pass
    
    def close(self) -> None:
        """Optional cleanup for adapters with resources."""
        pass


class GmgnAdapter(SecurityAdapter):
    """GMGN API adapter (stub implementation).
    
    This is a mock/stub implementation for testing and development.
    In production, this would make actual API calls to GMGN.
    
    Expected response structure:
    {
        "is_honeypot": bool,
        "freeze_authority": Optional[bool],
        "mint_authority": Optional[bool],
        "top_holders_pct": float
    }
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """Initialize GMGN adapter.
        
        Args:
            api_key: Optional API key for authenticated requests
            base_url: Optional custom base URL for the API
        """
        self.api_key = api_key
        self.base_url = base_url or "https://api.gmgn.io/v1"
        self._mock_mode = True  # Stub by default
    
    def fetch_security_info(self, mint: str) -> Dict[str, Any]:
        """Fetch security info (mock implementation).
        
        In a real implementation, this would:
        1. Build the API request URL
        2. Add authentication headers
        3. Make HTTP request
        4. Parse and return security fields
        
        Returns:
            Mock security data for the token
        """
        # Stub: Return mock data based on mint hash for determinism
        # This ensures consistent behavior across runs
        mint_hash = hash(mint)
        
        # Use mint_hash to deterministically assign security flags
        # This is just for testing - real API would return actual data
        is_honeypot = (mint_hash % 7) == 0  # ~14% honeypot rate
        freeze_authority = (mint_hash % 5) == 0  # ~20% have freeze
        mint_authority = (mint_hash % 11) == 0  # ~9% have mint auth
        
        # Top holders percentage (deterministic float)
        top_holders_pct = round((abs(mint_hash) % 100) / 100.0, 2)
        
        return {
            "is_honeypot": is_honeypot,
            "freeze_authority": freeze_authority,
            "mint_authority": mint_authority,
            "top_holders_pct": top_holders_pct,
            "provider": "gmgn",
            "mint": mint,
        }
    
    def close(self) -> None:
        """Clean up adapter resources."""
        pass


class RugCheckAdapter(SecurityAdapter):
    """RugCheck API adapter (stub implementation).
    
    Similar to GmgnAdapter, this provides a mock interface for testing.
    
    Expected response structure:
    {
        "is_honeypot": bool,
        "top_holders": {...},
        "risk_score": int,
        "flags": list[str]
    }
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize RugCheck adapter."""
        self.api_key = api_key
        self._mock_mode = True
    
    def fetch_security_info(self, mint: str) -> Dict[str, Any]:
        """Fetch security info (mock implementation)."""
        mint_hash = hash(mint)
        
        is_honeypot = (mint_hash % 7) == 0
        freeze_authority = (mint_hash % 5) == 0
        mint_authority = (mint_hash % 11) == 0
        top_holders_pct = round((abs(mint_hash) % 100) / 100.0, 2)
        
        # RugCheck specific fields
        risk_score = 0 if not is_honeypot else 100
        flags = []
        if is_honeypot:
            flags.append("honeypot")
        if freeze_authority:
            flags.append("freeze_authority")
        if mint_authority:
            flags.append("mint_authority")
        
        return {
            "is_honeypot": is_honeypot,
            "freeze_authority": freeze_authority,
            "mint_authority": mint_authority,
            "top_holders_pct": top_holders_pct,
            "risk_score": risk_score,
            "flags": flags,
            "provider": "rugcheck",
            "mint": mint,
        }
    
    def close(self) -> None:
        pass


def get_adapter(provider: str = "gmgn", **kwargs) -> SecurityAdapter:
    """Factory function to get a security adapter by provider name.
    
    Args:
        provider: Provider name ("gmgn", "rugcheck")
        **kwargs: Additional arguments passed to adapter constructor
        
    Returns:
        SecurityAdapter instance
    """
    providers = {
        "gmgn": GmgnAdapter,
        "rugcheck": RugCheckAdapter,
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown security provider: {provider}. Available: {list(providers.keys())}")
    
    return providers[provider](**kwargs)
