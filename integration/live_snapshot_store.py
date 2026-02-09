"""integration/live_snapshot_store.py

Live token snapshot store that fetches price data from Jupiter API.

P0 goals:
- HTTP GET calls to Jupiter API for real-time price data.
- In-memory TTL cache (default 30 seconds) per mint.
- Returns TokenSnapshot with price data in extra field.
- Fail-safe: Returns None on any network error.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from requests.exceptions import RequestException

from integration.token_snapshot_store import TokenSnapshot


class LiveTokenSnapshotStore:
    """Fetches and caches live token snapshots from Jupiter API."""

    JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"

    def __init__(self, ttl_seconds: int = 30):
        """Initialize the store with TTL cache.

        Args:
            ttl_seconds: Time-to-live for cached data in seconds (default: 30).
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, mint: str) -> Optional[TokenSnapshot]:
        """Fetch and cache token data for the given mint.

        Args:
            mint: The token mint address.

        Returns:
            TokenSnapshot with price data if successful, None on error.
        """
        if not mint:
            self._log_error("get called with empty mint")
            return None

        # Check cache validity
        now = time.time()
        cached = self._cache.get(mint)
        cached_ts = self._cache_timestamps.get(mint)

        if cached is not None and cached_ts is not None:
            if now - cached_ts < self._ttl_seconds:
                return self._build_snapshot(mint, cached)

        # Fetch fresh data from Jupiter API
        try:
            response = requests.get(
                self.JUPITER_PRICE_URL,
                params={"ids": mint},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            self._log_request(f"GET {self.JUPITER_PRICE_URL}?ids={mint} -> 200")

            # Cache the result
            self._cache[mint] = data
            self._cache_timestamps[mint] = now

            return self._build_snapshot(mint, data)

        except RequestException as e:
            self._log_error(f"HTTP error for mint {mint}: {e}")
            return None
        except (ValueError, KeyError) as e:
            self._log_error(f"Parse error for mint {mint}: {e}")
            return None

    def _build_snapshot(self, mint: str, data: Dict[str, Any]) -> TokenSnapshot:
        """Build a TokenSnapshot from Jupiter API response.

        Args:
            mint: The token mint address.
            data: The parsed JSON response from Jupiter API.

        Returns:
            TokenSnapshot with price data extracted.
        """
        # Extract price data from Jupiter response format
        extra: Dict[str, Any] = {}

        # Jupiter API v2 response format: {"data": {<mint>: {"price": "..."}}}
        data_body = data.get("data", {})
        mint_data = data_body.get(mint, {})

        price = mint_data.get("price")
        if price is not None:
            try:
                extra["price"] = float(price)
            except (ValueError, TypeError):
                extra["price"] = None

        # Include the raw mint data in extra for debugging
        extra["jupiter_raw"] = mint_data

        return TokenSnapshot(
            mint=mint,
            ts_snapshot=datetime.utcnow().isoformat() + "Z",
            liquidity_usd=None,  # Jupiter price API doesn't provide liquidity
            extra=extra if extra else None,
        )

    def _log_request(self, message: str) -> None:
        """Log a request message to stderr."""
        print(f"[LiveSnapshotStore] {message}", file=sys.stderr)

    def _log_error(self, message: str) -> None:
        """Log an error message to stderr."""
        print(f"[LiveSnapshotStore] ERROR: {message}", file=sys.stderr)

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._cache_timestamps.clear()
