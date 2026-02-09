"""ingestion/sources/rpc_source.py

RpcSource: JSON-RPC ingestion from Solana RPC endpoints.
Implements TradeSource interface for live trade ingestion.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

from .base import TradeSource


class RpcSource(TradeSource):
    """TradeSource implementation using Solana JSON-RPC API.

    Polls getSignaturesForAddress for tracked wallets and normalizes
    responses to trade dict format compatible with trade_schema.json.

    Environment:
        SOLANA_RPC_URL: RPC endpoint URL (default: https://api.mainnet-beta.solana.com)
    """

    DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_BEFORE_SLOT = None  # Start from latest, works backward
    MAX_SIGNATURES_PER_REQUEST = 1000

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        tracked_wallets: Optional[List[str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        before_slot: Optional[int] = None,
        limit_per_wallet: Optional[int] = None,
    ):
        """Initialize RpcSource.

        Args:
            rpc_url: Solana RPC endpoint URL. Reads SOLANA_RPC_URL from env if None.
            tracked_wallets: List of wallet addresses to track.
            timeout: Request timeout in seconds.
            before_slot: Start fetching signatures before this slot (pagination).
            limit_per_wallet: Max signatures to fetch per wallet (None = unlimited).
        """
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL", self.DEFAULT_RPC_URL)
        self.tracked_wallets = tracked_wallets or []
        self.timeout = timeout
        self.before_slot = before_slot
        self.limit_per_wallet = limit_per_wallet
        self._session = requests.Session()

    def _make_request(
        self, method: str, params: List[Any] = None
    ) -> Dict[str, Any]:
        """Make JSON-RPC request with error handling and backoff."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }

        backoff = 1.0
        max_backoff = 60.0

        while True:
            try:
                response = self._session.post(
                    self.rpc_url,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    error_code = result.get("error", {}).get("code", -1)
                    # Handle rate limits (429) and server errors (500)
                    if error_code == 429 or response.status_code in (429, 500):
                        time.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)
                        continue
                    raise requests.HTTPError(
                        f"JSON-RPC error: {result['error']}",
                        response=response,
                    )

                return result.get("result", {})

            except requests.exceptions.ConnectionError as e:
                print(f"[RpcSource] Connection error: {e}", file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except requests.exceptions.Timeout as e:
                print(f"[RpcSource] Request timeout: {e}", file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code in (429, 500):
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue
                print(f"[RpcSource] HTTP error: {e}", file=sys.stderr)
                raise

    def _fetch_signatures_for_address(
        self, wallet: str, before: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch transaction signatures for a wallet address."""
        params = [wallet, {"limit": self.MAX_SIGNATURES_PER_REQUEST}]
        if before is not None:
            params[1]["before"] = before

        result = self._make_request("getSignaturesForAddress", params)
        return result.get("signatures", [])

    def _normalize_signature_to_trade(
        self, wallet: str, signature_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize getSignaturesForAddress response to trade dict.

        Note: getSignaturesForAddress returns metadata only. To get full
        trade details, callers should fetch the transaction and parse it.
        This provides a base record with available metadata.
        """
        # Extract available fields
        signature = signature_data.get("signature", "")
        slot = signature_data.get("slot")
        err = signature_data.get("err")
        memo = signature_data.get("memo")

        # Parse timestamp if available
        ts = signature_data.get("blockTime")
        if ts is not None:
            # blockTime is Unix seconds
            ts_str = str(ts)
        else:
            # Fallback: use current time if blockTime not available
            ts_str = str(int(time.time()))

        # Determine side from memo or err (heuristic)
        # Full side determination requires parsing the transaction
        side = "BUY"  # Default, should be refined with tx parsing
        if memo:
            if "sell" in memo.lower():
                side = "SELL"
            elif "buy" in memo.lower():
                side = "BUY"

        # Placeholder values - actual price/size require tx parsing
        # These will be filled in by downstream processing
        trade = {
            "ts": ts_str,
            "wallet": wallet,
            "mint": "",  # To be filled from transaction
            "side": side,
            "price": 0.0,  # To be filled from transaction
            "size_usd": 0.0,  # To be filled from transaction
            "tx_hash": signature,
            "slot": slot,
            "source": "rpc",
        }

        if err:
            trade["err"] = err
        if memo:
            trade["memo"] = memo

        return trade

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """Yield normalized trade dicts from tracked wallets.

        Yields:
            Dict[str, Any]: Trade records compatible with trade_schema.json.
        """
        fetched = 0

        for wallet in self.tracked_wallets:
            if self.limit_per_wallet is not None and fetched >= self.limit_per_wallet:
                break

            before = None
            wallet_count = 0

            while True:
                if (
                    self.limit_per_wallet is not None
                    and wallet_count >= self.limit_per_wallet
                ):
                    break

                try:
                    signatures = self._fetch_signatures_for_address(wallet, before)

                    if not signatures:
                        break

                    for sig_data in signatures:
                        trade = self._normalize_signature_to_trade(wallet, sig_data)
                        yield trade

                        wallet_count += 1
                        fetched += 1

                        if (
                            self.limit_per_wallet is not None
                            and fetched >= self.limit_per_wallet
                        ):
                            break

                    # Set up pagination for next batch
                    before = signatures[-1].get("signature")

                    # If fewer results than limit, we've reached the end
                    if len(signatures) < self.MAX_SIGNATURES_PER_REQUEST:
                        break

                except Exception as e:
                    print(f"[RpcSource] Error fetching for {wallet}: {e}", file=sys.stderr)
                    break

    def poll_new_records(
        self,
        wallet: str,
        stop_at_signature: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Poll for new records since last processed signature.

        Args:
            wallet: Wallet address to poll.
            stop_at_signature: Stop when reaching this signature (exclusive).
            limit: Maximum number of records to return.

        Returns:
            List of normalized trade dicts.
        """
        collected: List[Dict[str, Any]] = []

        try:
            signatures = self._fetch_signatures_for_address(wallet)

            for sig_data in signatures:
                sig = sig_data.get("signature", "")
                if sig == stop_at_signature:
                    break
                if len(collected) >= limit:
                    break

                trade = self._normalize_signature_to_trade(wallet, sig_data)
                collected.append(trade)

            return collected

        except Exception as e:
            print(f"[RpcSource] Error polling for {wallet}: {e}", file=sys.stderr)
            return []

    def close(self):
        """Close the underlying requests session."""
        self._session.close()


# Import sys for stderr
import sys
