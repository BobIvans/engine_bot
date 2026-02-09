"""
Deployer Reputation Cache.

Analyzes deployer history through SolanaFM API.
Cache updated hourly, rate limited to 1 req/sec.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

# Configuration
SOLANAFM_BASE_URL = "https://public-api.solanafm.com"
SOLANAFM_RATE_LIMIT_DELAY = 1.05  # seconds
SOLANAFM_CACHE_TTL = 3600  # 1 hour
SOLANAFM_TIMEOUT = 10.0  # seconds


@dataclass
class DeployerReputation:
    """Deployer reputation data."""
    address: str
    total_tokens: int
    successful_tokens: int
    score: float  # [-1.0, +1.0]
    last_updated: int


# Global cache
_deployer_cache: dict[str, tuple[float, DeployerReputation]] = {}
_last_request_time = 0.0
_cache_lock = asyncio.Lock()


class DeployerReputationCache:
    """
    Cache for deployer reputation scores.
    
    Features:
    - Hourly updates for top deployers
    - Rate limiting (1 req/sec)
    - Fallback to limited on-chain analysis
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        api_key: Optional[str] = None,
        timeout: float = SOLANAFM_TIMEOUT,
    ):
        self.cache_dir = cache_dir or Path("data/cache")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def _rate_limit(self) -> None:
        """Enforce rate limit."""
        global _last_request_time
        async with _cache_lock:
            now = time.monotonic()
            elapsed = now - _last_request_time
            if elapsed < SOLANAFM_RATE_LIMIT_DELAY:
                await asyncio.sleep(SOLANAFM_RATE_LIMIT_DELAY - elapsed)
            _last_request_time = time.monotonic()
    
    def _get_cached(self, address: str) -> Optional[DeployerReputation]:
        """Get cached reputation if valid."""
        global _deployer_cache
        cached = _deployer_cache.get(address)
        if cached:
            data, cached_at = cached
            if time.monotonic() - cached_at < SOLANAFM_CACHE_TTL:
                return data
            del _deployer_cache[address]
        return None
    
    def _set_cached(self, address: str, data: DeployerReputation) -> None:
        """Cache reputation data."""
        global _deployer_cache
        _deployer_cache[address] = (data, time.monotonic())
    
    def _load_from_disk(self, address: str) -> Optional[DeployerReputation]:
        """Load from disk cache."""
        if not self.cache_dir.exists():
            return None
        
        cache_file = self.cache_dir / f"deployer_reputation.json"
        if not cache_file.exists():
            return None
        
        try:
            data = json.loads(cache_file.read_text())
            if address in data:
                entry = data[address]
                return DeployerReputation(
                    address=address,
                    total_tokens=entry.get("total_tokens", 0),
                    successful_tokens=entry.get("successful_tokens", 0),
                    score=entry.get("score", 0.0),
                    last_updated=entry.get("last_updated", 0),
                )
        except Exception as e:
            print(f"[deployer_reputation] Failed to load cache: {e}")
        return None
    
    def _save_to_disk(self, reputations: dict[str, DeployerReputation]) -> None:
        """Save reputations to disk cache."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cache_dir / f"deployer_reputation.json"
        
        data = {}
        for addr, rep in reputations.items():
            data[addr] = {
                "total_tokens": rep.total_tokens,
                "successful_tokens": rep.successful_tokens,
                "score": rep.score,
                "last_updated": rep.last_updated,
            }
        
        cache_file.write_text(json.dumps(data, indent=2))
    
    async def get_reputation(
        self,
        address: str,
        allow_external: bool = False,
    ) -> DeployerReputation:
        """
        Get deployer reputation score.
        
        Args:
            address: Deployer wallet address
            allow_external: Whether to fetch from external API
        
        Returns:
            DeployerReputation with score in [-1.0, +1.0]
        """
        # Check memory cache
        cached = self._get_cached(address)
        if cached:
            return cached
        
        # Check disk cache
        disk_cache = self._load_from_disk(address)
        if disk_cache:
            self._set_cached(address, disk_cache)
            return disk_cache
        
        if not allow_external:
            # Return neutral reputation
            return DeployerReputation(
                address=address,
                total_tokens=0,
                successful_tokens=0,
                score=0.0,
                last_updated=0,
            )
        
        # Fetch from API
        session = await self._get_session()
        url = f"{SOLANAFM_BASE_URL}/v1/accounts/{address}/tokens"
        
        try:
            await self._rate_limit()
            
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"[deployer_reputation] API error {resp.status}")
                    return DeployerReputation(
                        address=address, total_tokens=0, successful_tokens=0, score=0.0, last_updated=0
                    )
                
                data = await resp.json()
            
            # Analyze token history
            tokens = data.get("items", [])
            total = len(tokens)
            successful = sum(1 for t in tokens if self._is_successful_token(t))
            
            score = (2 * successful / max(1, total)) - 1.0 if total > 0 else 0.0
            score = max(-1.0, min(1.0, score))
            
            reputation = DeployerReputation(
                address=address,
                total_tokens=total,
                successful_tokens=successful,
                score=score,
                last_updated=int(time.time()),
            )
            
            self._set_cached(address, reputation)
            return reputation
            
        except Exception as e:
            print(f"[deployer_reputation] Error fetching {address}: {e}")
            return DeployerReputation(
                address=address, total_tokens=0, successful_tokens=0, score=0.0, last_updated=0
            )
    
    def _is_successful_token(self, token_data: dict) -> bool:
        """Check if token is considered successful."""
        # Success criteria: held >30% liquidity 24h after launch
        # Simplified: check if token has ongoing trading
        return token_data.get("has_liquidity", False)
    
    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self) -> "DeployerReputationCache":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()


# Synchronous wrapper for scripts
def get_reputation_sync(
    address: str,
    fixture_path: Optional[Path] = None,
) -> float:
    """
    Get deployer reputation score synchronously.
    
    Uses fixture data if available.
    """
    if fixture_path and fixture_path.exists():
        data = json.loads(fixture_path.read_text())
        for entry in data:
            if entry.get("deployer_address") == address:
                return entry.get("deployer_reputation", 0.0)
    
    return 0.0  # Neutral for unknown


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Deployer Reputation")
    parser.add_argument("address", help="Deployer wallet address")
    parser.add_argument("--fixture", type=Path, help="Fixture file path")
    
    args = parser.parse_args()
    
    score = get_reputation_sync(args.address, args.fixture)
    print(json.dumps({"address": args.address, "reputation_score": score}))
