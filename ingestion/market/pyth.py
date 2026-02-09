"""
ingestion/market/pyth.py

Pyth Network Price Feed Client (Hermes API).

PR-T.3
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

from .pyth_ids import get_feed_id

logger = logging.getLogger(__name__)


# Hermes API Configuration
HERMES_BASE_URL = "https://hermes.pyth.network"
HERMES_V2_ENDPOINT = "/v2/updates/price/latest"

# Cache TTL
DEFAULT_CACHE_TTL = 5  # seconds


@dataclass
class PriceData:
    """Normalized price data from Pyth."""
    price: float          # Normalized price
    conf: float          # Confidence interval
    ts: int              # Unix timestamp
    status: str          # "trading" | "halted"
    raw_price: int       # Raw integer price from Pyth
    raw_expo: int        # Exponent
    feed_id: str         # Feed ID used
    symbol: str          # Symbol for display
    
    def is_safe(self, threshold: float = 0.01) -> bool:
        """
        Check if price confidence is within acceptable bounds.
        
        Args:
            threshold: Maximum confidence/price ratio (default 1%)
            
        Returns:
            True if confidence is acceptable
        """
        if self.price == 0:
            return False
        return (self.conf / self.price) <= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "price": self.price,
            "conf": self.conf,
            "ts": self.ts,
            "status": self.status,
            "feed_id": self.feed_id,
            "symbol": self.symbol,
        }


class PythClient:
    """
    Client for Pyth Network Hermes API.
    
    Features:
    - REST-based price fetching
    - Automatic normalization (price * 10^expo)
    - Confidence interval validation
    - Response caching
    
    PR-T.3
    """
    
    def __init__(
        self,
        base_url: str = HERMES_BASE_URL,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        request_timeout: float = 10.0,
    ):
        """
        Initialize PythClient.
        
        Args:
            base_url: Hermes API base URL
            cache_ttl: Cache TTL in seconds
            request_timeout: Request timeout in seconds
        """
        self._base_url = base_url
        self._cache_ttl = cache_ttl
        self._timeout = request_timeout
        
        # Cache for price data
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        
    def _get_cache_key(self, symbol: str) -> str:
        """Generate cache key for symbol."""
        return f"pyth:{symbol.upper()}"
    
    def _get_cached_price(self, symbol: str) -> Optional[PriceData]:
        """Get cached price if valid."""
        key = self._get_cache_key(symbol)
        cached = self._price_cache.get(key)
        
        if cached is None:
            return None
        
        # Check if cache is expired
        if time.time() - cached["cached_at"] > self._cache_ttl:
            del self._price_cache[key]
            return None
        
        return cached["data"]
    
    def _cache_price(self, symbol: str, data: PriceData) -> None:
        """Cache price data."""
        key = self._get_cache_key(symbol)
        self._price_cache[key] = {
            "data": data,
            "cached_at": time.time(),
        }
    
    def fetch_price(
        self,
        symbol: str,
        use_cache: bool = True,
        http_callable: Optional[Any] = None,
    ) -> Optional[PriceData]:
        """
        Fetch price for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "SOL/USD")
            use_cache: Whether to use cached data
            http_callable: Optional HTTP callable for testing (mock)
            
        Returns:
            PriceData or None if unavailable
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_price(symbol)
            if cached is not None:
                logger.debug(f"[pyth] Cache hit for {symbol}")
                return cached
        
        try:
            # Get feed ID
            feed_id = get_feed_id(symbol)
            
            # Build URL
            url = f"{self._base_url}{HERMES_V2_ENDPOINT}?ids[]={feed_id}"
            
            # Make request
            if http_callable is not None:
                # Use provided callable (for testing)
                response = http_callable(url)
            else:
                # Use requests library
                import requests
                response = requests.get(url, timeout=self._timeout)
                response.raise_for_status()
            
            # Parse response
            data = response.json()
            price_data = self._parse_hermes_response(data, symbol, feed_id)
            
            # Cache if valid
            if price_data is not None:
                self._cache_price(symbol, price_data)
            
            return price_data
            
        except Exception as e:
            logger.warning(f"[pyth] Failed to fetch price for {symbol}: {e}")
            return None
    
    def _parse_hermes_response(
        self,
        data: Dict[str, Any],
        symbol: str,
        feed_id: str,
    ) -> Optional[PriceData]:
        """
        Parse Hermes API response.
        
        Response format:
        {
            "data": {
                "0xfeed_id": {
                    "price": {
                        "price": 123456789,
                        "expo": -8,
                        "conf": 1234
                    },
                    "metadata": {
                        "ts": 1234567890
                    },
                    "status": "trading"
                }
            }
        }
        """
        try:
            # Get the nested price data
            feed_data = data.get("data", {}).get(feed_id)
            if feed_data is None:
                logger.warning(f"[pyth] No price data for {symbol} in response")
                return None
            
            price_info = feed_data.get("price", {})
            metadata = feed_data.get("metadata", {})
            status = feed_data.get("status", "unknown")
            
            # Extract values
            raw_price = price_info.get("price", 0)
            raw_expo = price_info.get("expo", 0)
            conf = price_info.get("conf", 0)
            ts = metadata.get("ts", int(time.time()))
            
            # Normalize price: price * 10^expo
            # expo is typically negative for USD prices (e.g., -8 for SOL/USD)
            normalized_price = raw_price * (10 ** raw_expo)
            normalized_conf = abs(conf * (10 ** raw_expo))
            
            # Handle trading status
            trading_status = "trading" if status == "trading" else "halted"
            
            return PriceData(
                price=float(normalized_price),
                conf=float(normalized_conf),
                ts=ts,
                status=trading_status,
                raw_price=raw_price,
                raw_expo=raw_expo,
                feed_id=feed_id,
                symbol=symbol,
            )
            
        except Exception as e:
            logger.error(f"[pyth] Failed to parse response: {e}")
            return None
    
    def fetch_multiple(
        self,
        symbols: list,
        http_callable: Optional[Any] = None,
    ) -> Dict[str, PriceData]:
        """
        Fetch prices for multiple symbols.
        
        Args:
            symbols: List of trading pairs
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Dict mapping symbol to PriceData
        """
        results = {}
        
        for symbol in symbols:
            price = self.fetch_price(symbol, http_callable=http_callable)
            if price is not None:
                results[symbol] = price
        
        return results
    
    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear price cache.
        
        Args:
            symbol: Specific symbol to clear, or None to clear all
        """
        if symbol is None:
            self._price_cache.clear()
            logger.debug("[pyth] Cache cleared")
        else:
            key = self._get_cache_key(symbol)
            if key in self._price_cache:
                del self._price_cache[key]
                logger.debug(f"[pyth] Cache cleared for {symbol}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cached_items": len(self._price_cache),
            "cache_ttl": self._cache_ttl,
        }
