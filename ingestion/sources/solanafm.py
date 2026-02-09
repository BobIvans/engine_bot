"""
SolanaFM Token Enrichment Adapter

Optional adapter for enriching token data via public SolanaFM API.
Provides: verified status, creator_address, holder_distribution, 
mint_authority, freeze_authority with rate limiting and caching.

API Docs: https://docs.solanafm.com/
Rate Limit: 1 request/second max
TTL: 3600s for success, 300s for errors
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import aiohttp

from strategy.schemas.solanafm_enrichment_schema import (
    validate_solanafm_enrichment,
    SolanaFMEnrichment,
)


# Configuration
SOLANAFM_BASE_URL = "https://public-api.solanafm.com"
SOLANAFM_RATE_LIMIT_DELAY = 1.1  # seconds (slightly > 1 req/sec to be safe)
SOLANAFM_SUCCESS_TTL = 3600  # 1 hour
SOLANAFM_ERROR_TTL = 300  # 5 minutes
SOLANAFM_TIMEOUT = 10.0  # seconds


@dataclass
class CachedEnrichment:
    """Wrapper for cached enrichment data with timestamp."""
    data: SolanaFMEnrichment
    cached_at: float


# Global cache - in production, use Redis
_enrichment_cache: dict[str, CachedEnrichment] = {}
_last_request_time = 0.0
_cache_lock = asyncio.Lock()


@dataclass
class SolanaFMEnricher:
    """
    Client for enriching token data via SolanaFM API.
    
    Features:
    - Rate limiting (1 req/sec)
    - In-memory caching with TTL
    - Graceful degradation on API errors
    - Optional fixture mode for testing
    """
    
    api_key: Optional[str] = None
    base_url: str = SOLANAFM_BASE_URL
    timeout: float = SOLANAFM_TIMEOUT
    use_fixtures: bool = False
    fixture_path: Optional[Path] = None
    
    def __post_init__(self):
        """Initialize session and load fixtures if needed."""
        self._session: Optional[aiohttp.ClientSession] = None
        self._fixtures: dict[str, SolanaFMEnrichment] = {}
        
        if self.use_fixtures and self.fixture_path:
            self._load_fixtures()
    
    def _load_fixtures(self) -> None:
        """Load fixture data for testing."""
        if self.fixture_path and self.fixture_path.exists():
            try:
                data = json.loads(self.fixture_path.read_text())
                for item in data:
                    enrichment = SolanaFMEnrichment(**item)
                    self._fixtures[enrichment.mint] = enrichment
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"[solanafm] Warning: Failed to load fixtures: {e}")
    
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
        """Enforce rate limit of 1 request/second."""
        global _last_request_time
        async with _cache_lock:
            now = time.monotonic()
            elapsed = now - _last_request_time
            if elapsed < SOLANAFM_RATE_LIMIT_DELAY:
                await asyncio.sleep(SOLANAFM_RATE_LIMIT_DELAY - elapsed)
            _last_request_time = time.monotonic()
    
    def _get_cached(self, mint: str) -> Optional[SolanaFMEnrichment]:
        """Get cached enrichment if valid."""
        global _enrichment_cache
        cached = _enrichment_cache.get(mint)
        if cached:
            now = time.monotonic()
            ttl = SOLANAFM_SUCCESS_TTL if cached.data.is_verified else SOLANAFM_ERROR_TTL
            if now - cached.cached_at < ttl:
                return cached.data
            del _enrichment_cache[mint]
        return None
    
    def _set_cached(self, mint: str, data: SolanaFMEnrichment) -> None:
        """Cache enrichment data."""
        global _enrichment_cache
        _enrichment_cache[mint] = CachedEnrichment(data=data, cached_at=time.monotonic())
    
    async def _fetch_from_api(self, mint: str) -> Optional[SolanaFMEnrichment]:
        """Fetch enrichment data from SolanaFM API."""
        session = await self._get_session()
        
        # Get token metadata
        metadata_url = f"{self.base_url}/v1/tokens/{mint}/metadata"
        # Get holder info
        holders_url = f"{self.base_url}/v1/tokens/{mint}/holders"
        
        try:
            await self._rate_limit()
            
            # Fetch metadata
            async with session.get(metadata_url) as resp:
                if resp.status == 404:
                    # Token not found - return minimal enrichment
                    return SolanaFMEnrichment(
                        mint=mint,
                        is_verified=False,
                        creator_address=None,
                        top_holder_pct=100.0,
                        holder_count=0,
                        has_mint_authority=False,
                        has_freeze_authority=False,
                        enrichment_ts=int(time.time()),
                        source="api_not_found"
                    )
                elif resp.status != 200:
                    print(f"[solanafm] API error {resp.status} for {mint}")
                    return None
                
                metadata = await resp.json()
            
            # Fetch holders
            await self._rate_limit()
            async with session.get(holders_url) as holders_resp:
                if holders_resp.status != 200:
                    print(f"[solanafm] Holders API error {holders_resp.status} for {mint}")
                    holders_data = {"total": 0, "items": []}
                else:
                    holders_data = await holders_resp.json()
            
            # Parse response and build enrichment
            token_info = metadata.get("data", metadata)
            
            # Extract authorities
            mint_authority = token_info.get("mintAuthority")
            freeze_authority = token_info.get("freezeAuthority")
            
            # Calculate top holder percentage
            total_supply = float(token_info.get("supply", 0) or 0)
            holders = holders_data.get("items", [])
            top_holder_amount = 0.0
            for h in holders[:10]:  # Check top 10 holders
                top_holder_amount += float(h.get("amount", 0) or 0)
            
            top_holder_pct = 0.0
            if total_supply > 0:
                top_holder_pct = (top_holder_amount / total_supply) * 100
            
            enrichment = SolanaFMEnrichment(
                mint=mint,
                is_verified=token_info.get("verified", False),
                creator_address=token_info.get("creators", [{}])[0].get("address") if token_info.get("creators") else None,
                top_holder_pct=round(top_holder_pct, 2),
                holder_count=holders_data.get("total", len(holders)),
                has_mint_authority=mint_authority is not None,
                has_freeze_authority=freeze_authority is not None,
                enrichment_ts=int(time.time()),
                source="api"
            )
            
            # Validate against schema
            validate_solanafm_enrichment(enrichment.dict())
            return enrichment
            
        except asyncio.TimeoutError:
            print(f"[solanafm] Timeout fetching {mint}")
            return None
        except aiohttp.ClientError as e:
            print(f"[solanafm] Client error for {mint}: {e}")
            return None
        except Exception as e:
            print(f"[solanafm] Unexpected error for {mint}: {e}")
            return None
    
    async def get_enrichment(self, mint: str) -> SolanaFMEnrichment:
        """
        Get enrichment for a token mint.
        
        Returns cached data if available, otherwise fetches from API
        or fixture. Falls back to minimal enrichment on failure.
        """
        # Check cache first
        cached = self._get_cached(mint)
        if cached:
            return cached
        
        # Return fixture if in fixture mode
        if self.use_fixtures and mint in self._fixtures:
            fixture = self._fixtures[mint]
            self._set_cached(mint, fixture)
            return fixture
        
        # Fetch from API
        result = await self._fetch_from_api(mint)
        
        if result is None:
            # Graceful degradation: return minimal enrichment
            result = SolanaFMEnrichment(
                mint=mint,
                is_verified=False,
                creator_address=None,
                top_holder_pct=100.0,
                holder_count=0,
                has_mint_authority=False,
                has_freeze_authority=False,
                enrichment_ts=int(time.time()),
                source="fallback"
            )
        
        # Cache the result
        self._set_cached(mint, result)
        return result
    
    async def get_enrichments_batch(self, mints: list[str]) -> dict[str, SolanaFMEnrichment]:
        """
        Get enrichment for multiple tokens concurrently.
        Respects rate limits across all requests.
        """
        results = {}
        for mint in mints:
            try:
                results[mint] = await self.get_enrichment(mint)
            except Exception as e:
                print(f"[solanafm] Error enriching {mint}: {e}")
                results[mint] = SolanaFMEnrichment(
                    mint=mint,
                    is_verified=False,
                    creator_address=None,
                    top_holder_pct=100.0,
                    holder_count=0,
                    has_mint_authority=False,
                    has_freeze_authority=False,
                    enrichment_ts=int(time.time()),
                    source="error"
                )
        return results
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self) -> "SolanaFMEnricher":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()


# Synchronous wrapper for scripts
def load_from_fixture(fixture_path: Path) -> dict[str, SolanaFMEnrichment]:
    """
    Load enrichment data from fixture file (for testing).
    
    Returns dict mapping mint -> SolanaFMEnrichment
    """
    if not fixture_path.exists():
        return {}
    
    data = json.loads(fixture_path.read_text())
    return {item["mint"]: SolanaFMEnrichment(**item) for item in data}


# CLI interface
async def main():
    """CLI entry point for manual enrichment."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SolanaFM Token Enrichment")
    parser.add_argument("mint", nargs="+", help="Token mint(s) to enrich")
    parser.add_argument("--api-key", help="SolanaFM API key")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--fixture", action="store_true", help="Use fixture mode for testing")
    parser.add_argument("--fixture-path", type=Path, help="Path to fixture file")
    
    args = parser.parse_args()
    
    enricher = SolanaFMEnricher(
        api_key=args.api_key,
        use_fixtures=args.fixture,
        fixture_path=args.fixture_path
    )
    
    async with enricher:
        results = await enricher.get_enrichments_batch(args.mint)
    
    output = {mint: data.dict() for mint, data in results.items()}
    
    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2))
        print(f"Wrote results to {args.output}")
    else:
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
