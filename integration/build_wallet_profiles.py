#!/usr/bin/env python3
"""integration/build_wallet_profiles.py

CLI tool to aggregate trades into wallet profiles.

Usage:
    python -m integration.build_wallet_profiles --trades <path> --out <path>

Args:
    --trades: Path to input trades file (JSONL or Parquet)
    --out: Path to output wallet profiles (CSV or Parquet)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterator, List, Union

from integration.trade_normalizer import load_trades_jsonl, normalize_trade_record
from integration.parquet_io import iter_parquet_records, ParquetReadConfig
from strategy.profiling import aggregate_wallet_stats
from integration.wallet_profile_store import WalletProfile


def iter_trades_from_path(path: str) -> Iterator[Union[dict, tuple[dict, int]]]:
    """Iterate trades from JSONL or Parquet file.

    Yields:
        For JSONL: (record_dict, lineno)
        For Parquet: record_dict (lineno not available)
    """
    path_obj = Path(path)
    if path_obj.suffix.lower() == ".parquet":
        cfg = ParquetReadConfig(path=path)
        for record in iter_parquet_records(cfg):
            yield record
    else:
        # Assume JSONL
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                import json
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"Error: Failed to parse JSON line {lineno}: {e}", file=sys.stderr)
                    continue
                yield record, lineno


def check_pnl_usd_warning(trade: dict) -> None:
    """Check if pnl_usd is missing and warn to stderr."""
    extra = trade.get("extra")
    if not extra or "pnl_usd" not in extra:
        print(
            f"Warning: Missing 'pnl_usd' in trade extra for wallet={trade.get('wallet')}, tx={trade.get('tx_hash')}",
            file=sys.stderr,
        )


def write_profiles_csv(profiles: List[WalletProfile], path: str) -> None:
    """Write wallet profiles to CSV file."""
    fieldnames = ["wallet", "tier", "roi_30d_pct", "winrate_30d", "trades_30d", "median_hold_sec", "avg_trade_size_sol"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in profiles:
            writer.writerow({
                "wallet": p.wallet,
                "tier": p.tier if p.tier is not None else "",
                "roi_30d_pct": p.roi_30d_pct if p.roi_30d_pct is not None else "",
                "winrate_30d": p.winrate_30d if p.winrate_30d is not None else "",
                "trades_30d": p.trades_30d if p.trades_30d is not None else "",
                "median_hold_sec": p.median_hold_sec if p.median_hold_sec is not None else "",
                "avg_trade_size_sol": p.avg_trade_size_sol if p.avg_trade_size_sol is not None else "",
            })


def write_profiles_parquet(profiles: List[WalletProfile], path: str) -> None:
    """Write wallet profiles to Parquet file."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        # Fallback to duckdb if pyarrow not available
        try:
            import duckdb
        except ImportError:
            raise RuntimeError("Either pyarrow or duckdb is required for Parquet output")

        records = [
            {
                "wallet": p.wallet,
                "tier": p.tier,
                "roi_30d_pct": p.roi_30d_pct,
                "winrate_30d": p.winrate_30d,
                "trades_30d": p.trades_30d,
                "median_hold_sec": p.median_hold_sec,
                "avg_trade_size_sol": p.avg_trade_size_sol,
            }
            for p in profiles
        ]
        con = duckdb.connect(database=":memory:")
        con.execute("CREATE TABLE profiles AS SELECT * FROM records")
        con.execute(f"COPY profiles TO '{path}' (FORMAT PARQUET)")
        return

    # Use pyarrow
    data = {
        "wallet": [p.wallet for p in profiles],
        "tier": [p.tier for p in profiles],
        "roi_30d_pct": [p.roi_30d_pct for p in profiles],
        "winrate_30d": [p.winrate_30d for p in profiles],
        "trades_30d": [p.trades_30d for p in profiles],
        "median_hold_sec": [p.median_hold_sec for p in profiles],
        "avg_trade_size_sol": [p.avg_trade_size_sol for p in profiles],
    }
    table = pa.Table.from_pydict(data)
    pq.write_table(table, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate trades into wallet profiles")
    parser.add_argument("--trades", required=True, help="Path to input trades file (JSONL or Parquet)")
    parser.add_argument("--out", required=True, help="Path to output wallet profiles (CSV or Parquet)")
    args = parser.parse_args()

    # Load and normalize trades
    trades = []
    for item in iter_trades_from_path(args.trades):
        if isinstance(item, tuple):
            record, lineno = item
        else:
            record = item
            lineno = None

        # Check for pnl_usd warning
        check_pnl_usd_warning(record)

        # Normalize trade
        trade = normalize_trade_record(record, lineno=lineno or 0)
        if isinstance(trade, dict) and trade.get("_reject"):
            # Skip rejected trades
            continue
        trades.append(trade)

    # Aggregate wallet stats
    profiles = aggregate_wallet_stats(trades)

    # Write output
    out_path = Path(args.out)
    if out_path.suffix.lower() == ".parquet":
        write_profiles_parquet(profiles, args.out)
    else:
        write_profiles_csv(profiles, args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
