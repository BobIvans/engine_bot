"""Token State Provider with caching and adapter orchestration.

Provides a unified interface for fetching token state data with:
- In-memory caching with TTL support
- Primary/Secondary adapter orchestration
- Rate limit protection via adapter's min_interval_sec
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from integration.token_snapshot_store import TokenSnapshot
from .adapters import BaseAdapter, DexScreenerAdapter, JupiterAdapter


class TokenStateProvider:
    """Unified provider for token state data with caching and orchestration.

    Uses a primary adapter (Jupiter) for price data and optionally enriches
    with a secondary adapter (DexScreener) for additional metrics.
    """

    DEFAULT_TTL_SEC: float = 30.0

    def __init__(
        self,
        primary_adapter: Optional[JupiterAdapter] = None,
        secondary_adapter: Optional[DexScreenerAdapter] = None,
        ttl_sec: float = DEFAULT_TTL_SEC,
    ) -> None:
        """Initialize the token state provider.

        Args:
            primary_adapter: Primary adapter for fetching price data.
                Defaults to JupiterAdapter with default rate limiting.
            secondary_adapter: Optional secondary adapter for enrichment.
                When provided, fetched data will be merged with primary data.
            ttl_sec: Cache TTL in seconds. Defaults to 30 seconds.
        """
        self._primary_adapter = primary_adapter or JupiterAdapter()
        self._secondary_adapter = secondary_adapter
        self._ttl_sec = ttl_sec
        self._cache: Dict[str, Tuple[float, TokenSnapshot]] = {}

    def get_snapshot(self, mint: str) -> Optional[TokenSnapshot]:
        """Fetch token snapshot for the given mint address.

        Implements the following flow:
        1. Check cache; if valid, return cached data
        2. Call Primary adapter (Jupiter) for price data
        3. If secondary adapter is configured, call it for enrichment
        4. Update cache with merged data
        5. Return TokenSnapshot

        Args:
            mint: The token mint address to fetch data for.

        Returns:
            TokenSnapshot with available data, or None if fetch fails.
        """
        # Check cache first
        cached = self._cache.get(mint)
        if cached is not None:
            expire_ts, snapshot = cached
            if time.time() < expire_ts:
                return snapshot
            # Cache expired, remove entry
            del self._cache[mint]

        # Fetch from primary adapter
        try:
            primary_data = self._primary_adapter.fetch(mint)
        except Exception:
            primary_data = {}

        # Fetch from secondary adapter for enrichment if configured
        if self._secondary_adapter is not None:
            try:
                secondary_data = self._secondary_adapter.fetch(mint)
            except Exception:
                secondary_data = {}
        else:
            secondary_data = {}

        # Merge data: secondary enriches primary
        merged_data = {**primary_data, **secondary_data}

        # Build TokenSnapshot from merged data
        snapshot = self._build_snapshot(mint, merged_data)

        # Update cache
        expire_ts = time.time() + self._ttl_sec
        self._cache[mint] = (expire_ts, snapshot)

        return snapshot

    def _build_snapshot(self, mint: str, data: Dict[str, Any]) -> TokenSnapshot:
        """Build TokenSnapshot from adapter response data.

        Args:
            mint: The token mint address.
            data: Merged data from adapters.

        Returns:
            TokenSnapshot instance with available fields populated.
        """
        # Handle price_usd - may come as string from APIs
        price_usd = data.get("price_usd")
        if price_usd is not None:
            try:
                price_usd = float(price_usd)
            except (TypeError, ValueError):
                price_usd = None

        # Handle ts_snapshot - use current time if not provided
        ts_snapshot = data.get("ts_snapshot")
        if ts_snapshot is None:
            ts_snapshot = int(time.time())
        elif not isinstance(ts_snapshot, str):
            ts_snapshot = str(ts_snapshot)

        return TokenSnapshot(
            mint=mint,
            ts_snapshot=ts_snapshot,
            liquidity_usd=data.get("liquidity_usd"),
            volume_24h_usd=data.get("volume_24h_usd"),
            spread_bps=None,  # Not provided by current adapters
            top10_holders_pct=None,  # Not provided by current adapters
            single_holder_pct=None,  # Not provided by current adapters
            extra={"source": "token_state_provider"},
        )

    def invalidate(self, mint: str) -> bool:
        """Remove cached snapshot for the given mint.

        Args:
            mint: The token mint address to invalidate.

        Returns:
            True if an entry was removed, False if no cached entry existed.
        """
        if mint in self._cache:
            del self._cache[mint]
            return True
        return False

    def clear_cache(self) -> None:
        """Clear all cached snapshots."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Return the number of cached entries."""
        return len(self._cache)

    def get_primary_adapter(self) -> BaseAdapter:
        """Return the primary adapter instance."""
        return self._primary_adapter

    def get_secondary_adapter(self) -> Optional[BaseAdapter]:
        """Return the secondary adapter instance, if configured."""
        return self._secondary_adapter
