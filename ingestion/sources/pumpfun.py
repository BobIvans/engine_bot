"""
Pump.fun Launch Detection Adapter.

Detects token launches via Pump.fun program events.
Public API: https://frontend-api.pump.fun/coins/{mint}
Rate limit: 1 request/sec, cache: 3600s
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

# Configuration
PUMPFUN_API_URL = "https://frontend-api.pump.fun"
PUMPFUN_RATE_LIMIT_DELAY = 1.05  # seconds
PUMPFUN_CACHE_TTL = 3600  # 1 hour
PUMPFUN_TIMEOUT = 10.0  # seconds


@dataclass
class PumpFunCoinData:
    """Pump.fun coin information."""
    mint: str
    name: str
    symbol: str
    description: str
    image_uri: str
    created_timestamp: int
    raydium_pool: Optional[str] = None
    total_supply: Optional[float] = None


# Global cache
_pumpfun_cache: dict[str, tuple[float, PumpFunCoinData]] = {}
_last_request_time = 0.0
_cache_lock = asyncio.Lock()


class PumpFunDetector:
    """
    Detector for Pump.fun token launches.
    
    Features:
    - Rate limiting (1 req/sec)
    - In-memory caching (1 hour TTL)
    - Graceful degradation on API errors
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        timeout: float = PUMPFUN_TIMEOUT,
    ):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def _rate_limit(self) -> None:
        """Enforce rate limit."""
        global _last_request_time
        async with _cache_lock:
            now = time.monotonic()
            elapsed = now - _last_request_time
            if elapsed < PUMPFUN_RATE_LIMIT_DELAY:
                await asyncio.sleep(PUMPFUN_RATE_LIMIT_DELAY - elapsed)
            _last_request_time = time.monotonic()
    
    def _get_cached(self, mint: str) -> Optional[PumpFunCoinData]:
        """Get cached data if valid."""
        global _pumpfun_cache
        cached = _pumpfun_cache.get(mint)
        if cached:
            data, cached_at = cached
            if time.monotonic() - cached_at < PUMPFUN_CACHE_TTL:
                return data
            del _pumpfun_cache[mint]
        return None
    
    def _set_cached(self, mint: str, data: PumpFunCoinData) -> None:
        """Cache data."""
        global _pumpfun_cache
        _pumpfun_cache[mint] = (data, time.monotonic())
    
    async def get_coin_data(self, mint: str) -> Optional[PumpFunCoinData]:
        """
        Get Pump.fun coin data by mint address.
        
        Returns None if not found or API error.
        """
        # Check cache
        cached = self._get_cached(mint)
        if cached:
            return cached
        
        # Fetch from API
        session = await self._get_session()
        url = f"{PUMPFUN_API_URL}/coins/{mint}"
        
        try:
            await self._rate_limit()
            
            async with session.get(url) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    print(f"[pumpfun] API error {resp.status} for {mint}")
                    return None
                
                data = await resp.json()
            
            coin = PumpFunCoinData(
                mint=data.get("mint", mint),
                name=data.get("name", ""),
                symbol=data.get("symbol", ""),
                description=data.get("description", ""),
                image_uri=data.get("image_uri", ""),
                created_timestamp=data.get("created_timestamp", 0),
                raydium_pool=data.get("raydium_pool"),
                total_supply=data.get("total_supply"),
            )
            
            self._set_cached(mint, coin)
            return coin
            
        except asyncio.TimeoutError:
            print(f"[pumpfun] Timeout fetching {mint}")
            return None
        except Exception as e:
            print(f"[pumpfun] Error fetching {mint}: {e}")
            return None
    
    async def detect_launch(self, mint: str) -> Optional[tuple[int, str]]:
        """
        Detect launch timestamp and source for a token.
        
        Returns: (timestamp_ms, source_hint) or None if not a Pump.fun launch
        """
        coin_data = await self.get_coin_data(mint)
        
        if coin_data is None:
            return None
        
        if coin_data.created_timestamp > 0:
            return (coin_data.created_timestamp * 1000, "pump_fun")
        
        return None
    
    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self) -> "PumpFunDetector":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()


# Synchronous wrapper for scripts
def detect_launch_sync(mint: str, fixture_path: Optional[Path] = None) -> tuple[int, str]:
    """
    Synchronous launch detection for scripts.
    
    Uses fixture data if available, otherwise returns default.
    """
    if fixture_path and fixture_path.exists():
        data = json.loads(fixture_path.read_text())
        for coin in data:
            if coin.get("mint") == mint:
                return (coin.get("created_timestamp", 0) * 1000, "pump_fun")
    
    # Default fallback (conservative: unknown)
    return (0, "unknown")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pump.fun Launch Detection")
    parser.add_argument("mint", help="Token mint address")
    parser.add_argument("--fixture", type=Path, help="Fixture file path")
    
    args = parser.parse_args()
    
    result = detect_launch_sync(args.mint, args.fixture)
    print(json.dumps({"launch_ts": result[0], "source": result[1]}))
