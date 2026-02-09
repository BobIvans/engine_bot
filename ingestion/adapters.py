"""Token State Adapters for Jupiter and DexScreener APIs.

Provides abstract base class and concrete implementations for fetching
token price and liquidity data from external APIs.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import requests


class BaseAdapter(ABC):
    """Abstract base class for token state API adapters.

    Provides rate limit protection via configurable minimum interval
    between API calls.
    """

    def __init__(self, min_interval_sec: float = 0.5) -> None:
        """Initialize adapter with rate limit settings.

        Args:
            min_interval_sec: Minimum seconds between API calls to prevent
                rate limiting. Defaults to 0.5 seconds.
        """
        self._min_interval_sec = min_interval_sec
        self._last_call_ts: Optional[float] = None

    def _rate_limit(self) -> None:
        """Enforce minimum interval between API calls."""
        if self._last_call_ts is not None:
            elapsed = time.time() - self._last_call_ts
            if elapsed < self._min_interval_sec:
                time.sleep(self._min_interval_sec - elapsed)
        self._last_call_ts = time.time()

    @abstractmethod
    def fetch(self, mint: str) -> Dict[str, Any]:
        """Fetch token state data for the given mint address.

        Args:
            mint: The token mint address to fetch data for.

        Returns:
            Dictionary containing token state data. Concrete adapters
            determine the specific fields returned.
        """
        pass


class JupiterAdapter(BaseAdapter):
    """Adapter for Jupiter Price API v2.

    Fetches price data from Jupiter aggregator.
    API Endpoint: https://api.jup.ag/price/v2?ids={mint}
    """

    BASE_URL = "https://api.jup.ag/price/v2"

    def fetch(self, mint: str) -> Dict[str, Any]:
        """Fetch price data from Jupiter API.

        Args:
            mint: The token mint address.

        Returns:
            Dictionary with:
                - price_usd: Token price in USD
                - mint: Token mint address
                - ts_snapshot: Unix timestamp of the fetch
                - liquidity_usd: Always None (not provided by this API)
        """
        self._rate_limit()

        url = f"{self.BASE_URL}?ids={mint}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        token_data = data.get("data", {}).get(mint, {})

        return {
            "price_usd": token_data.get("price"),
            "mint": mint,
            "ts_snapshot": int(time.time()),
            "liquidity_usd": None,
        }


class DexScreenerAdapter(BaseAdapter):
    """Adapter for DexScreener Latest Dex Tokens API.

    Fetches token metadata including price, liquidity, and volume.
    API Endpoint: https://api.dexscreener.com/latest/dex/tokens/{mint}
    """

    BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"

    def fetch(self, mint: str) -> Dict[str, Any]:
        """Fetch token data from DexScreener API.

        Args:
            mint: The token mint address.

        Returns:
            Dictionary with:
                - price_usd: Token price in USD
                - liquidity_usd: Total liquidity in USD
                - volume_24h_usd: 24-hour trading volume in USD
        """
        self._rate_limit()

        url = f"{self.BASE_URL}/{mint}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        token_data = data.get("pair", {})

        return {
            "price_usd": token_data.get("priceUsd"),
            "liquidity_usd": token_data.get("liquidity", {}).get("usd"),
            "volume_24h_usd": token_data.get("volume", {}).get("h24"),
        }
