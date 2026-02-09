"""ingestion/sources/flipside.py

PR-WD.2: Flipside Solana.ez_dex_swaps Alternative Fetcher.

Parallel data source for wallet discovery through Flipside Crypto.
Extracts ROI/winrate/median_hold metrics from historical swaps,
normalizes to canonical wallet_profile format, and serves as
fallback/verification to Dune.

Supports two modes:
1. Local fixture for tests (default)
2. Real Flipside API (optional, via --use-api flag)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Schema version constant
SCHEMA_VERSION = "wallet_profile.v1"

# Expected output columns for wallet_profile schema
WALLET_PROFILE_COLUMNS = [
    "wallet_addr",
    "roi_30d",
    "winrate_30d",
    "trades_30d",
    "median_hold_sec",
    "avg_size_usd",
    "preferred_dex",
    "memecoin_ratio",
]


@dataclass(frozen=True)
class WalletProfile:
    """Canonical wallet profile schema."""
    wallet_addr: str
    roi_30d: Optional[float] = None
    winrate_30d: Optional[float] = None
    trades_30d: Optional[int] = None
    median_hold_sec: Optional[float] = None
    avg_size_usd: Optional[float] = None
    preferred_dex: Optional[str] = None
    memecoin_ratio: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV/Parquet export."""
        return {
            "wallet_addr": self.wallet_addr,
            "roi_30d": self.roi_30d,
            "winrate_30d": self.winrate_30d,
            "trades_30d": self.trades_30d,
            "median_hold_sec": self.median_hold_sec,
            "avg_size_usd": self.avg_size_usd,
            "preferred_dex": self.preferred_dex,
            "memecoin_ratio": self.memecoin_ratio,
        }


class FlipsideWalletSource:
    """Flipside source adapter for wallet profile discovery."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Flipside source adapter.

        Args:
            api_key: Optional Flipside API key for real API access.
        """
        self.api_key = api_key
        self._base_url = "https://api.flipsidecrypto.com"

    def load_from_file(self, path: str) -> List[WalletProfile]:
        """Load wallet profiles from CSV/JSON fixture file.

        Args:
            path: Path to fixture file (CSV or JSONL format).

        Returns:
            List of normalized WalletProfile objects.

        Raises:
            FileNotFoundError: If fixture file doesn't exist.
            ValueError: If file format is invalid.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {path}")

        profiles: List[WalletProfile] = []

        if path.endswith(".csv"):
            profiles = self._load_from_csv(path)
        elif path.endswith(".jsonl"):
            profiles = self._load_from_jsonl(path)
        else:
            # Try CSV first, then JSONL
            try:
                profiles = self._load_from_csv(path)
            except Exception:
                profiles = self._load_from_jsonl(path)

        return profiles

    def _load_from_csv(self, path: str) -> List[WalletProfile]:
        """Load wallet profiles from CSV file."""
        profiles: List[WalletProfile] = []

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                profile = normalize_flipside_row(row)
                if profile is not None:
                    profiles.append(profile)

        return profiles

    def _load_from_jsonl(self, path: str) -> List[WalletProfile]:
        """Load wallet profiles from JSONL file."""
        profiles: List[WalletProfile] = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    profile = normalize_flipside_row(row)
                    if profile is not None:
                        profiles.append(profile)
                except json.JSONDecodeError:
                    continue

        return profiles

    def export_to_parquet(
        self,
        profiles: List[WalletProfile],
        out_path: str,
        dry_run: bool = False
    ) -> None:
        """Export wallet profiles to Parquet file.

        Args:
            profiles: List of WalletProfile objects to export.
            out_path: Output file path for Parquet file.
            dry_run: If True, don't write to filesystem (validation only).
        """
        if dry_run:
            print(f"[flipside] DRY RUN: Would write {len(profiles)} profiles to {out_path}",
                  file=sys.stderr)
            return

        try:
            import duckdb  # type: ignore
        except ImportError:
            print("[flipside] ERROR: duckdb required for Parquet export", file=sys.stderr)
            sys.exit(1)

        # Convert profiles to records
        records = [p.to_dict() for p in profiles]

        # Create temporary Parquet file using DuckDB
        con = duckdb.connect(database=":memory:")

        # Create table and insert records
        con.execute("CREATE TABLE profiles AS SELECT * FROM records")

        # Write to Parquet
        con.execute(f"COPY profiles TO '{out_path}' (FORMAT PARQUET)")

        print(f"[flipside] Exported {len(profiles)} profiles to {out_path}", file=sys.stderr)

    def fetch_from_api(
        self,
        query: str,
        max_rows: int = 10000
    ) -> List[WalletProfile]:
        """Fetch wallet profiles from Flipside API.

        Args:
            query: SQL query for Flipside (must target solana.ez_dex_swaps).
            max_rows: Maximum number of rows to return.

        Returns:
            List of normalized WalletProfile objects.

        Raises:
            ValueError: If API key is not configured.
            RuntimeError: If API request fails.
        """
        if not self.api_key:
            raise ValueError(
                "Flipside API key required for API access. "
                "Set FLIPSIDE_API_KEY environment variable or pass --api-key."
            )

        import time

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        # Submit query
        submit_url = f"{self._base_url}/api/v1/queries"
        submit_data = {
            "sql": query,
            "maxRowsPerTable": str(max_rows),
            "ttlMinutes": 60,
        }

        response = requests.post(
            submit_url,
            headers=headers,
            json=submit_data,
            timeout=30
        )
        response.raise_for_status()

        query_result = response.json()
        query_id = query_result.get("data", {}).get("queryId")

        if not query_id:
            raise RuntimeError(f"Failed to get query ID: {query_result}")

        # Poll for results
        status_url = f"{self._base_url}/api/v1/queries/{query_id}"
        max_attempts = 30
        attempt = 0

        while attempt < max_attempts:
            time.sleep(2)
            response = requests.get(status_url, headers=headers, timeout=30)
            response.raise_for_status()

            result = response.json()
            status = result.get("data", {}).get("status", {}).get("state")

            if status == "COMPLETED":
                break
            elif status in ["FAILED", "CANCELLED"]:
                raise RuntimeError(f"Query {status}: {result}")

            attempt += 1

        # Get results
        results_url = f"{self._base_url}/api/v1/queries/{query_id}/results"
        response = requests.get(results_url, headers=headers, timeout=30)
        response.raise_for_status()

        result = response.json()
        rows = result.get("data", {}).get("rows", [])

        profiles: List[WalletProfile] = []
        for row in rows:
            profile = normalize_flipside_row(row)
            if profile is not None:
                profiles.append(profile)

        return profiles


def normalize_flipside_row(row: Dict[str, Any]) -> Optional[WalletProfile]:
    """Normalize a Flipside row to WalletProfile schema.

    Maps Flipside solana.ez_dex_swaps columns to canonical wallet_profile format:
    - swapper -> wallet_addr
    - roi_30d -> roi_30d (or pnl_percentage)
    - winrate_30d -> winrate_30d
    - trades_30d -> trades_30d
    - median_hold_sec -> median_hold_sec
    - avg_size_usd -> avg_size_usd
    - preferred_dex -> preferred_dex
    - memecoin_ratio -> memecoin_ratio (calculated from memecoin_swaps/total_swaps)

    Args:
        row: Dictionary from Flipside CSV/JSONL.

    Returns:
        WalletProfile if row is valid, None if validation fails.
    """
    # Extract wallet address
    wallet_addr = row.get("swapper") or row.get("wallet_addr") or row.get("wallet")
    if not wallet_addr:
        return None

    wallet_addr = str(wallet_addr).strip()
    if not wallet_addr:
        return None

    # Extract and validate numeric fields
    try:
        roi_30d = _parse_float(row.get("roi_30d") or row.get("pnl_percentage") or row.get("roi"))
        winrate_30d = _parse_float(row.get("winrate_30d") or row.get("winrate"))
        trades_30d = _parse_int(row.get("trades_30d") or row.get("trades") or row.get("trade_count"))
        median_hold_sec = _parse_float(row.get("median_hold_sec") or row.get("median_hold"))
        avg_size_usd = _parse_float(row.get("avg_size_usd") or row.get("avg_size") or row.get("avg_trade_size_usd"))
        memecoin_ratio = _parse_float(row.get("memecoin_ratio"))

        # Calculate memecoin_ratio from swap counts if not provided
        if memecoin_ratio is None:
            memecoin_swaps = _parse_int(row.get("memecoin_swaps") or row.get("memecoin_count"))
            total_swaps = _parse_int(row.get("total_swaps") or row.get("swaps"))
            if memecoin_swaps is not None and total_swaps is not None and total_swaps > 0:
                memecoin_ratio = memecoin_swaps / total_swaps

    except (ValueError, TypeError):
        return None

    # Validate ranges
    if winrate_30d is not None:
        if not (0.0 <= winrate_30d <= 1.0):
            return None

    if trades_30d is not None and trades_30d < 0:
        return None

    if median_hold_sec is not None and median_hold_sec < 0:
        return None

    # Extract preferred DEX
    preferred_dex = row.get("preferred_dex") or row.get("dex") or row.get("platform")
    if preferred_dex:
        preferred_dex = str(preferred_dex).strip()
        if not preferred_dex:
            preferred_dex = None

    return WalletProfile(
        wallet_addr=wallet_addr,
        roi_30d=roi_30d,
        winrate_30d=winrate_30d,
        trades_30d=trades_30d,
        median_hold_sec=median_hold_sec,
        avg_size_usd=avg_size_usd,
        preferred_dex=preferred_dex,
        memecoin_ratio=memecoin_ratio,
    )


def _parse_float(value: Any) -> Optional[float]:
    """Parse a value to float, returning None if invalid."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"nan", "none", "null", ""}:
            return None
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _parse_int(value: Any) -> Optional[int]:
    """Parse a value to int, returning None if invalid."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"nan", "none", "null", ""}:
            return None
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return None
    return None


def main() -> int:
    """CLI entry point for Flipside wallet source."""
    parser = argparse.ArgumentParser(
        description="Flipside Solana Wallet Fetcher - PR-WD.2"
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to fixture file (CSV/JSONL)"
    )
    parser.add_argument(
        "--out-path",
        default="-",
        help="Output file path for Parquet (default: stdout as JSONL)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing to filesystem"
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Print summary metrics as JSON to stdout"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Flipside API key for real API access"
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use Flipside API instead of fixture file"
    )
    parser.add_argument(
        "--api-query",
        default=None,
        help="SQL query for Flipside API (required with --use-api)"
    )

    args = parser.parse_args()

    try:
        # Load profiles
        if args.use_api:
            if not args.api_key:
                args.api_key = os.environ.get("FLIPSIDE_API_KEY")
            source = FlipsideWalletSource(api_key=args.api_key)
            if not args.api_query:
                parser.error("--api-query required with --use-api")
            profiles = source.fetch_from_api(args.api_query)
        else:
            source = FlipsideWalletSource()
            profiles = source.load_from_file(args.input_file)

        # Export to Parquet if specified
        if args.out_path != "-" and not args.dry_run:
            source.export_to_parquet(profiles, args.out_path, dry_run=False)

        # Output to stdout
        if args.out_path == "-" or args.dry_run:
            for profile in profiles:
                if args.dry_run:
                    print(f"[dry-run] {json.dumps(profile.to_dict())}", file=sys.stderr)
                else:
                    print(json.dumps(profile.to_dict()))

        # Summary JSON to stdout
        if args.summary_json:
            summary = {
                "exported_count": len(profiles),
                "schema_version": SCHEMA_VERSION,
            }
            print(json.dumps(summary))

        # Final status to stderr
        if not args.summary_json:
            print(
                f"[flipside] Processed {len(profiles)} wallets, schema={SCHEMA_VERSION}",
                file=sys.stderr
            )

        return 0

    except Exception as e:
        print(f"[flipside] ERROR: {e}", file=sys.stderr)
        return 1


# Import for API support
import os
import requests  # noqa: F401 (lazy import)
