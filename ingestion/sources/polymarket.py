"""ingestion/sources/polymarket.py

PR-F.3 Polymarket Regime Overlay - Polymarket API client.
PR-PM.1 Polymarket Gamma API Snapshot Fetcher.

Free/Read-Only: Uses public Polymarket Gamma API (or equivalent free endpoints).
No paid keys required.

Handles rate limits and errors gracefully.
Includes mock mode for testing without network.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# Polymarket API endpoints (public)
POLYMARKET_API_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_MARKETS_ENDPOINT = f"{POLYMARKET_API_BASE}/markets"

# Schema version for snapshots
SCHEMA_VERSION = "polymarket_snapshot.v1"


class PolymarketClient:
    """Polymarket API client with mock support for testing."""

    def __init__(
        self,
        api_base: str = POLYMARKET_API_BASE,
        timeout_ms: int = 2000,
        rate_limit_delay: float = 0.1,
        mock_file: Optional[str] = None,
    ):
        """Initialize the Polymarket client.

        Args:
            api_base: Base URL for the API.
            timeout_ms: Request timeout in milliseconds (default: 2 seconds).
            rate_limit_delay: Delay between requests to respect rate limits.
            mock_file: Path to JSON file with mock response data.
        """
        self.api_base = api_base
        self.timeout_ms = timeout_ms
        self.rate_limit_delay = rate_limit_delay
        self.mock_file = mock_file
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = now

    def _make_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a GET request to the Polymarket API.

        Args:
            url: Full URL for the request.
            params: Optional query parameters.

        Returns:
            Market/event dict, or error fallback on failure.
        """
        # Mock mode - return data from file
        if self.mock_file:
            mock_path = Path(self.mock_file)
            if mock_path.exists():
                with open(mock_path, "r") as f:
                    return json.load(f)
            # Return error fallback if mock file not found
            return self._error_fallback("MOCK_FILE_NOT_FOUND")

        self._rate_limit()

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout_ms / 1000.0,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list) and len(data) > 0:
                return data[0]
            return self._error_fallback("EMPTY_RESPONSE")
        except requests.exceptions.Timeout:
            return self._error_fallback("TIMEOUT")
        except requests.exceptions.RequestException as e:
            return self._error_fallback(f"REQUEST_ERROR: {str(e)}")

    def _error_fallback(self, error_type: str) -> Dict[str, Any]:
        """Return fallback data when API call fails.

        Args:
            error_type: Type of error that occurred.

        Returns:
            Fallback dict with data_quality="missing".
        """
        return {
            "p_yes": None,
            "p_no": None,
            "p_crash": None,
            "data_quality": "missing",
            "error": error_type,
        }

    def fetch_market(self, market_id: str) -> Dict[str, Any]:
        """Fetch market data by ID.

        Args:
            market_id: Polymarket market ID.

        Returns:
            Market dict with fields:
            - p_yes: Probability of YES outcome
            - p_no: Probability of NO outcome
            - p_crash: Optional crash probability
            - data_quality: "ok" | "missing"
        """
        params = {"id": market_id}
        return self._make_request(
            f"{self.api_base}/markets",
            params=params,
        )

    def fetch_by_slug(self, slug: str) -> Dict[str, Any]:
        """Fetch market data by slug.

        Args:
            slug: Market slug (URL-friendly identifier).

        Returns:
            Market dict with fields.
        """
        params = {"slug": slug}
        return self._make_request(
            f"{self.api_base}/markets",
            params=params,
        )

    def extract_probabilities(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardized probabilities from market data.

        Args:
            market: Market dict from API.

        Returns:
            Dict with p_yes, p_no, p_crash, data_quality.
        """
        # Extract YES probability
        p_yes = None
        for key in ["probability", "outcome", "yes_price", "yesPrice", "p_yes"]:
            if key in market:
                try:
                    p_yes = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Extract NO probability
        p_no = None
        for key in ["no_price", "noPrice", "p_no"]:
            if key in market:
                try:
                    p_no = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Calculate from YES if NO not available
        if p_yes is not None and p_no is None:
            p_no = 1.0 - p_yes

        # Extract crash probability
        p_crash = None
        for key in ["crash_probability", "p_crash", "crashProb"]:
            if key in market:
                try:
                    p_crash = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Determine data quality
        data_quality = "ok" if p_yes is not None else "missing"

        return {
            "p_yes": p_yes,
            "p_no": p_no,
            "p_crash": p_crash,
            "data_quality": data_quality,
        }


# ============================================================================
# PR-PM.1: Polymarket Snapshot Fetcher
# ============================================================================

class PolymarketSnapshotFetcher:
    """Fetches and normalizes Polymarket market snapshots.
    
    Supports both fixture-based (offline) and real API modes.
    """
    
    def __init__(self):
        """Initialize the snapshot fetcher."""
        self.client = PolymarketClient()
    
    def load_from_file(
        self,
        path: str,
        fixed_ts: Optional[int] = None,
    ) -> List["strategy.sentiment.PolymarketSnapshot"]:
        """Load and normalize snapshots from a fixture file.
        
        Args:
            path: Path to JSON fixture file.
            fixed_ts: Optional fixed timestamp for idempotent snapshots.
        
        Returns:
            List of normalized PolymarketSnapshot objects.
        """
        from strategy.sentiment import normalize_polymarket_market
        
        # Use fixed_ts or current time
        snapshot_ts = fixed_ts if fixed_ts is not None else int(time.time() * 1000)
        
        fixture_path = Path(path)
        if not fixture_path.exists():
            print(f"[polymarket_fetcher] WARNING: Fixture file not found: {path}", file=sys.stderr)
            return []
        
        with open(fixture_path, "r") as f:
            raw_markets = json.load(f)
        
        if not isinstance(raw_markets, list):
            raw_markets = [raw_markets]
        
        snapshots = []
        for raw in raw_markets:
            try:
                snapshot = normalize_polymarket_market(raw, snapshot_ts)
                snapshots.append(snapshot)
            except (ValueError, KeyError) as e:
                print(f"[polymarket_fetcher] WARNING: Skipping market due to error: {e}", file=sys.stderr)
                continue
        
        return snapshots
    
    def fetch_realtime(
        self,
        allow_polymarket: bool = False,
        fixed_ts: Optional[int] = None,
    ) -> List["strategy.sentiment.PolymarketSnapshot"]:
        """Fetch real-time snapshots from Polymarket API.
        
        Args:
            allow_polymarket: Whether to allow API calls (default: False).
            fixed_ts: Optional fixed timestamp for idempotent snapshots.
        
        Returns:
            List of normalized PolymarketSnapshot objects.
        """
        from strategy.sentiment import normalize_polymarket_market
        
        if not allow_polymarket:
            return []
        
        snapshot_ts = fixed_ts if fixed_ts is not None else int(time.time() * 1000)
        
        try:
            # Fetch active markets from Gamma API
            response = requests.get(
                POLYMARKET_MARKETS_ENDPOINT,
                params={"active": "true"},
                timeout=5.0,
            )
            
            if response.status_code == 429:
                print("[polymarket_fetcher] WARNING: Rate limited by Polymarket API (429)", file=sys.stderr)
                return []
            
            if response.status_code >= 500:
                print(f"[polymarket_fetcher] WARNING: Polymarket API error ({response.status_code})", file=sys.stderr)
                return []
            
            response.raise_for_status()
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, dict) and "data" in data:
                raw_markets = data["data"]
            elif isinstance(data, list):
                raw_markets = data
            else:
                print("[polymarket_fetcher] WARNING: Unexpected API response format", file=sys.stderr)
                return []
            
            snapshots = []
            for raw in raw_markets:
                try:
                    snapshot = normalize_polymarket_market(raw, snapshot_ts)
                    snapshots.append(snapshot)
                except (ValueError, KeyError) as e:
                    print(f"[polymarket_fetcher] WARNING: Skipping market due to error: {e}", file=sys.stderr)
                    continue
            
            return snapshots
            
        except requests.exceptions.Timeout:
            print("[polymarket_fetcher] WARNING: Polymarket API timeout", file=sys.stderr)
            return []
        except requests.exceptions.RequestException as e:
            print(f"[polymarket_fetcher] WARNING: Polymarket API request error: {e}", file=sys.stderr)
            return []
    
    def export_to_parquet(
        self,
        snapshots: List["strategy.sentiment.PolymarketSnapshot"],
        out_path: str,
        dry_run: bool = False,
    ) -> None:
        """Export snapshots to Parquet format.
        
        Args:
            snapshots: List of PolymarketSnapshot objects.
            out_path: Output file path.
            dry_run: If True, don't write file.
        """
        if dry_run:
            return
        
        if not snapshots:
            return
        
        # Import here to avoid dependency issues in dry-run mode
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            print("[polymarket_fetcher] WARNING: pyarrow not available, skipping parquet export", file=sys.stderr)
            return
        
        # Convert snapshots to record batches
        data = {
            "ts": [s.ts for s in snapshots],
            "market_id": [s.market_id for s in snapshots],
            "question": [s.question for s in snapshots],
            "p_yes": [s.p_yes for s in snapshots],
            "p_no": [s.p_no for s in snapshots],
            "volume_usd": [s.volume_usd for s in snapshots],
            "event_date": [s.event_date for s in snapshots],
            "category_tags": [s.category_tags for s in snapshots],
        }
        
        table = pa.Table.from_pydict(data)
        pq.write_table(table, out_path)


def main():
    """CLI entry point for Polymarket snapshot fetcher."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fetch Polymarket market snapshots"
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to fixture JSON file (for offline mode)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="polymarket_snapshots.parquet",
        help="Output Parquet file path",
    )
    parser.add_argument(
        "--fixed-ts",
        type=int,
        help="Fixed timestamp in milliseconds (for idempotent snapshots)",
    )
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="Allow real API calls (disabled by default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write output files",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output summary as JSON to stdout",
    )
    
    args = parser.parse_args()
    
    fetcher = PolymarketSnapshotFetcher()
    
    # Determine snapshot timestamp
    snapshot_ts = args.fixed_ts if args.fixed_ts else int(time.time() * 1000)
    
    # Load from fixture or API
    if args.input_file:
        snapshots = fetcher.load_from_file(args.input_file, args.fixed_ts)
    elif args.allow_api:
        snapshots = fetcher.fetch_realtime(allow_polymarket=True, fixed_ts=args.fixed_ts)
    else:
        print("[polymarket_fetcher] ERROR: Must specify --input-file or --allow-api", file=sys.stderr)
        sys.exit(1)
    
    # Export to parquet
    fetcher.export_to_parquet(snapshots, args.output, dry_run=args.dry_run)
    
    # Output summary
    if args.summary_json:
        import json
        summary = {
            "snapshot_count": len(snapshots),
            "ts": snapshot_ts,
            "schema_version": SCHEMA_VERSION,
        }
        print(json.dumps(summary))
    
    # Log summary
    print(f"[polymarket_fetcher] Fetched {len(snapshots)} snapshots", file=sys.stderr)


# Legacy class name for backwards compatibility
PolymarketSource = PolymarketClient


# Utility function to extract YES probability from market data
def extract_yes_probability(market: Dict[str, Any]) -> float:
    """Extract YES probability from a Polymarket market dict.

    Args:
        market: Market dict from API.

    Returns:
        YES probability (0.0 to 1.0), defaults to 0.5 if not found.
    """
    client = PolymarketClient()
    probs = client.extract_probabilities(market)
    return probs["p_yes"] if probs["p_yes"] is not None else 0.5
