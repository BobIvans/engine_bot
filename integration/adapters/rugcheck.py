#!/usr/bin/env python3
"""
RugCheck API HTTP Client with fail-safe logic.

Features:
- Retry with exponential backoff for rate limits (429)
- Fail-open: returns neutral score (0.5) on 5xx or timeout
- In-memory caching to avoid repeated API calls
"""

import json
import time
from typing import Dict, Optional
import urllib.request
import urllib.error


# Default configuration
DEFAULT_BASE_URL = "https://api.rugcheck.xyz/v1"
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_INITIAL = 1.0  # seconds


class RugCheckClient:
    """
    HTTP client for RugCheck API.
    
    Attributes:
        base_url: API base URL
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        backoff_initial: Initial backoff delay
        cache: In-memory LRU cache for results
    """
    
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_initial: float = DEFAULT_BACKOFF_INITIAL,
        cache_size: int = 1000,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_initial = backoff_initial
        self._cache: Dict[str, dict] = {}
        self._cache_size = cache_size
    
    def _get_cache_key(self, mint: str) -> str:
        """Generate cache key for a mint."""
        return f"rugcheck:{mint}"
    
    def _get_cached(self, mint: str) -> Optional[dict]:
        """Get cached result for a mint."""
        return self._cache.get(self._get_cache_key(mint))
    
    def _set_cached(self, mint: str, result: dict) -> None:
        """Cache result for a mint."""
        key = self._get_cache_key(mint)
        
        # Simple cache eviction
        if len(self._cache) >= self._cache_size:
            # Remove oldest entry (first key)
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        
        self._cache[key] = result
    
    def _make_request(self, url: str) -> Optional[dict]:
        """
        Make HTTP request with error handling.
        
        Returns:
            Parsed JSON dict, or None on failure
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited - will retry
                return None
            elif 500 <= e.code <= 599:
                # Server error - fail open
                return None
            else:
                return None
        
        except urllib.error.URLError:
            # Network error - fail open
            return None
        
        except TimeoutError:
            # Timeout - fail open
            return None
        
        except json.JSONDecodeError:
            # Invalid JSON - fail open
            return None
    
    def _fetch_with_retry(self, mint: str) -> Optional[dict]:
        """
        Fetch risk profile with exponential backoff retry.
        
        Returns:
            Raw API response dict, or None after retries exhausted
        """
        url = f"{self.base_url}/tokens/{mint}"
        
        for attempt in range(self.max_retries):
            result = self._make_request(url)
            
            if result is not None:
                return result
            
            if attempt < self.max_retries - 1:
                # Exponential backoff
                delay = self.backoff_initial * (2 ** attempt)
                time.sleep(delay)
        
        return None
    
    def get_risk_profile(self, mint: str) -> dict:
        """
        Get risk profile for a token mint.
        
        Args:
            mint: Token mint address
            
        Returns:
            Risk profile dict with score, flags, and metadata.
            On API failure, returns neutral profile (score=0.5).
        """
        # Check cache first
        cached = self._get_cached(mint)
        if cached is not None:
            return cached
        
        # Fetch from API with retry
        raw_result = self._fetch_with_retry(mint)
        
        if raw_result is None:
            # Fail-open: return neutral profile
            neutral_profile = {
                "mint": mint,
                "provider": "rugcheck",
                "score": 0.5,  # Neutral/Unknown
                "flags": ["api_unavailable"],
                "timestamp": int(time.time()),
                "is_verified": False,
                "top_holder_concentration": 0.0,
            }
            self._set_cached(mint, neutral_profile)
            return neutral_profile
        
        # Cache and return raw result (will be normalized by caller)
        self._set_cached(mint, raw_result)
        return raw_result
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._cache_size,
        }


if __name__ == "__main__":
    # Demo usage
    client = RugCheckClient()
    
    # Test with a known token (will fail in demo, but shows flow)
    # print(client.get_risk_profile("So11111111111111111111111111111111111111112"))
    print("RugCheckClient initialized successfully")
    print(f"Cache stats: {client.get_cache_stats()}")
