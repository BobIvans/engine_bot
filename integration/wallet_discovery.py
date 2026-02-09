#!/usr/bin/env python3
"""integration/wallet_discovery.py

PR-H.1 Wallet Discovery Pipeline (Offline Filter).

CLI utility for filtering raw wallet lists (e.g., exports from Dune/Kolscan):
- Reads CSV/JSONL input with wallet metrics
- Applies filters from config (ROI, winrate, trades)
- Outputs candidates without manual allowlist editing
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, TextIO


@dataclass
class WalletDiscoverySummary:
    """Summary statistics for wallet discovery run."""
    total_wallets: int = 0
    filtered_by_roi: int = 0
    filtered_by_winrate: int = 0
    filtered_by_trades: int = 0
    filtered_by_age: int = 0
    filtered_by_size: int = 0
    accepted: int = 0
    candidates: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_wallets": self.total_wallets,
            "filtered_by_roi": self.filtered_by_roi,
            "filtered_by_winrate": self.filtered_by_winrate,
            "filtered_by_trades": self.filtered_by_trades,
            "filtered_by_age": self.filtered_by_age,
            "filtered_by_size": self.filtered_by_size,
            "accepted": self.accepted,
        }


def load_config_filters(config_path: str) -> Dict[str, Any]:
    """Load filter thresholds from config file."""
    from integration.config_loader import load_params_base

    loaded = load_params_base(config_path)
    filters = loaded.config.get("wallet_profile", {}).get("filters", {})
    return filters


def normalize_wallet_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize wallet record column names to standard format and convert types."""
    # Map various column name variations to standard names
    column_mappings = {
        "wallet": ["wallet", "address", "pubkey", "public_key"],
        "roi_30d": ["roi_30d", "roi_30d_pct", "roi_pct_30d", "roi"],
        "winrate": ["winrate", "winrate_30d", "winrate_pct", "win_pct"],
        "trades_30d": ["trades_30d", "trades", "num_trades", "trade_count"],
        "avg_trade_size": ["avg_trade_size", "avg_trade_size_sol", "avg_size_sol", "avg_size", "size_sol"],
        "wallet_age": ["wallet_age", "wallet_age_days", "age_days", "account_age", "age"],
    }

    normalized = {}
    for standard_name, variations in column_mappings.items():
        for var in variations:
            if var in record:
                value = record[var]
                # Convert to appropriate type
                if standard_name in ["roi_30d", "winrate", "avg_trade_size"]:
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        value = 0
                elif standard_name in ["trades_30d", "wallet_age"]:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        value = 0
                normalized[standard_name] = value
                break

    return normalized


def filter_wallet(record: Dict[str, Any], filters: Dict[str, Any]) -> tuple[bool, str]:
    """Apply filters to a single wallet record.

    Returns:
        Tuple of (passed: bool, reason: str)
    """
    # Parse numeric values
    try:
        roi = float(record.get("roi_30d", 0) or 0)
    except (ValueError, TypeError):
        roi = 0

    try:
        winrate = float(record.get("winrate", 0) or 0)
    except (ValueError, TypeError):
        winrate = 0

    try:
        trades = int(record.get("trades_30d", 0) or 0)
    except (ValueError, TypeError):
        trades = 0

    try:
        avg_size = float(record.get("avg_trade_size", 0) or 0)
    except (ValueError, TypeError):
        avg_size = 0

    try:
        age_days = int(record.get("wallet_age", 0) or 0)
    except (ValueError, TypeError):
        age_days = 0

    # Apply filters
    min_roi = float(filters.get("min_roi_30d_pct", 0))
    if roi < min_roi:
        return False, f"ROI {roi:.1f}% < {min_roi}% threshold"

    min_winrate = float(filters.get("min_winrate_30d", 0))
    if winrate < min_winrate:
        return False, f"Winrate {winrate:.1%} < {min_winrate:.1%} threshold"

    min_trades = int(filters.get("min_trades_30d", 0))
    if trades < min_trades:
        return False, f"Trades {trades} < {min_trades} threshold"

    min_size = float(filters.get("min_avg_trade_size_sol", 0))
    if avg_size < min_size:
        return False, f"Avg size {avg_size:.2f} SOL < {min_size:.2f} SOL threshold"

    min_age = int(filters.get("min_wallet_age_days", 0))
    if age_days < min_age:
        return False, f"Age {age_days} days < {min_age} days threshold"

    return True, ""


def discover_wallets(
    input_file: TextIO,
    config_path: str,
    existing_profiles: set | None = None,
) -> WalletDiscoverySummary:
    """Run wallet discovery pipeline.

    Args:
        input_file: File-like object with wallet records (CSV/JSONL).
        config_path: Path to config file with filter thresholds.
        existing_profiles: Set of wallet addresses already in profiles.

    Returns:
        Summary with statistics and candidate list.
    """
    filters = load_config_filters(config_path)
    summary = WalletDiscoverySummary()

    if existing_profiles is None:
        existing_profiles = set()

    # Detect input format
    first_line = input_file.readline().strip()
    input_file.seek(0)

    is_jsonl = first_line.startswith("{") or first_line.startswith("[")

    if is_jsonl:
        records = (json.loads(line) for line in input_file if line.strip())
    else:
        reader = csv.DictReader(input_file)
        records = (row for row in reader)

    for record in records:
        summary.total_wallets += 1

        # Normalize column names
        normalized = normalize_wallet_record(record)

        wallet = normalized.get("wallet", "")
        if not wallet:
            continue

        # Skip if already exists in profiles (idempotency)
        if wallet in existing_profiles:
            continue

        # Apply filters
        passed, reason = filter_wallet(normalized, filters)

        if passed:
            summary.accepted += 1
            summary.candidates.append({
                "wallet": wallet,
                "roi_30d": normalized.get("roi_30d", 0),
                "winrate": normalized.get("winrate", 0),
                "trades_30d": normalized.get("trades_30d", 0),
                "avg_trade_size": normalized.get("avg_trade_size", 0),
                "wallet_age": normalized.get("wallet_age", 0),
                "tier": "candidate",
            })
        else:
            # Count rejections by reason
            if "ROI" in reason:
                summary.filtered_by_roi += 1
            elif "Winrate" in reason:
                summary.filtered_by_winrate += 1
            elif "Trades" in reason:
                summary.filtered_by_trades += 1
            elif "size" in reason:
                summary.filtered_by_size += 1
            elif "Age" in reason:
                summary.filtered_by_age += 1

    return summary


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(
        description="Wallet Discovery Pipeline - Filter raw wallet lists"
    )
    ap.add_argument("--input", default="-", help="Input file (CSV/JSONL, default: stdin)")
    ap.add_argument("--config", default="strategy/config/params_base.yaml")
    ap.add_argument(
        "--existing-profiles",
        default="",
        help="Optional file with existing wallet profiles (one per line)",
    )
    ap.add_argument("--output", default="-", help="Output file (JSONL, default: stdout)")
    ap.add_argument(
        "--summary-json",
        action="store_true",
        help="Print summary statistics as JSON to stdout",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed rejection reasons to stderr",
    )
    # PR-WD.2: Flipside source integration
    ap.add_argument(
        "--skip-flipside",
        action="store_true",
        default=False,
        help="Skip Flipside source for wallet discovery (default: False)",
    )
    ap.add_argument(
        "--flipside-input",
        default="",
        help="Path to Flipside fixture/CSV file for wallet discovery",
    )
    # PR-WD.3: Kolscan source integration
    ap.add_argument(
        "--allow-kolscan",
        action="store_true",
        default=False,
        help="Enable real Kolscan API calls (disabled by default, requires --i-understand-scraping-risks)",
    )
    ap.add_argument(
        "--kolscan-input",
        default="",
        help="Path to Kolscan fixture/JSON file for wallet discovery",
    )
    ap.add_argument(
        "--i-understand-scraping-risks",
        action="store_true",
        default=False,
        help="Confirm understanding of Kolscan scraping risks (required with --allow-kolscan)",
    )
    # PR-WD.1: Dune source integration
    ap.add_argument(
        "--skip-dune",
        action="store_true",
        default=False,
        help="Skip Dune source for wallet discovery (default: False)",
    )
    ap.add_argument(
        "--dune-input",
        default="",
        help="Path to Dune fixture/CSV file for wallet discovery",
    )
    # PR-WD.4: Wallet clustering
    ap.add_argument(
        "--skip-clustering",
        action="store_true",
        default=False,
        help="Skip wallet clustering step (default: False)",
    )
    # PR-WD.5: Multi-source merge
    ap.add_argument(
        "--skip-merge",
        action="store_true",
        default=False,
        help="Skip wallet merge stage (default: False)",
    )
    # PR-PM.1: Polymarket snapshot fetcher
    ap.add_argument(
        "--allow-polymarket",
        action="store_true",
        default=False,
        help="Enable Polymarket API calls (disabled by default)",
    )    # PR-PM.2: Risk regime computation
    ap.add_argument(
        "--skip-regime",
        action="store_true",
        default=False,
        help="Skip risk regime computation stage (default: False)",
    )
    # PR-PM.3: Event risk detection
    ap.add_argument(
        "--skip-event-risk",
        action="store_true",
        default=False,
        help="Skip event risk detection stage (default: False)",
    )
    # PR-PM.4: Token mapping
    ap.add_argument(
        "--skip-token-mapping",
        action="store_true",
        default=False,
        help="Skip Polymarket → Solana token mapping stage (default: False)",
    )

    args = ap.parse_args()

    # Load existing profiles if provided
    existing_profiles: set = set()
    if args.existing_profiles:
        with open(args.existing_profiles) as f:
            for line in f:
                wallet = line.strip()
                if wallet:
                    existing_profiles.add(wallet)

    # Open input
    if args.input == "-":
        input_file = sys.stdin
    else:
        input_file = open(args.input)

    try:
        summary = discover_wallets(
            input_file=input_file,
            config_path=args.config,
            existing_profiles=existing_profiles,
        )
    finally:
        if args.input != "-":
            input_file.close()

    # Write output
    if args.output == "-":
        output_file = sys.stdout
    else:
        output_file = open(args.output, "w")

    try:
        for candidate in summary.candidates:
            output_file.write(json.dumps(candidate) + "\n")
    finally:
        if args.output != "-":
            output_file.close()

    # Print verbose rejections
    if args.verbose:
        print("[discovery] Verbose rejections not implemented in this version", file=sys.stderr)

    # Print summary
    if args.summary_json:
        print(json.dumps(summary.to_dict()))
    else:
        print(
            f"[discovery] Total: {summary.total_wallets}, "
            f"Accepted: {summary.accepted}, "
            f"Rejected: {summary.total_wallets - summary.accepted}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
