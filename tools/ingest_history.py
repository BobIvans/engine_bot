#!/usr/bin/env python3
"""tools/ingest_history.py

CLI tool for ingesting raw history data from Dune CSV exports.

Usage:
    python3 -m tools.ingest_history \
        --input /path/to/dune_export.csv \
        --format dune \
        --out /path/to/output.parquet

Arguments:
    --input: Path to input CSV/Parquet file
    --format: Format specifier (currently only 'dune' is supported)
    --out: Path to output Parquet file

Pipeline:
    1. Instantiate source (DuneSource)
    2. Iterate records and normalize via trade_normalizer.normalize_trade_record
    3. Filter invalid/rejected records (log to stderr)
    4. Write valid records to Parquet using duckdb
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from typing import Any, Dict, Iterator, List

from ingestion.sources.dune_source import DuneSource
from integration.trade_normalizer import Reject, normalize_trade_record
from integration.trade_types import Trade


def iter_source_records(input_path: str, fmt: str) -> Iterator[Dict[str, Any]]:
    """Yield raw records from the specified source format."""
    if fmt == "dune":
        source = DuneSource(input_path)
        yield from source.iter_records()
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def normalize_and_filter(
    records: Iterator[Dict[str, Any]],
) -> Iterator[Trade]:
    """Normalize records and yield only valid trades, logging rejects to stderr."""
    for raw in records:
        result = normalize_trade_record(raw)
        if isinstance(result, Reject):
            _log_reject(result)
        else:
            yield result


def _log_reject(reject: Reject) -> None:
    """Log a rejected record to stderr."""
    reason = reject.get("reason", "unknown")
    detail = reject.get("detail", "")
    lineno = reject.get("lineno", 0)
    msg = f"[reject] line={lineno} reason={reason} detail={detail}"
    print(msg, file=sys.stderr)


def write_parquet(trades: Iterator[Trade], output_path: str) -> int:
    """Write normalized trades to a Parquet file using duckdb."""
    import duckdb

    # Collect trades into a list for duckdb bulk insert
    trade_dicts = [asdict(t) for t in trades]

    if not trade_dicts:
        # Write empty parquet with expected schema
        empty_df = None
    else:
        # Create a DataFrame from the dicts using duckdb
        con = duckdb.connect(database=":memory:")
        con.register("trades_view", trade_dicts)
        empty_df = con.execute("SELECT * FROM trades_view LIMIT 0").fetchdf()

    # Write using duckdb COPY
    con = duckdb.connect(database=":memory:")
    if trade_dicts:
        con.register("trades_view", trade_dicts)
        sql = f"COPY (SELECT * FROM trades_view ORDER BY ts) TO '{output_path}' (FORMAT 'parquet')"
    else:
        # Create empty table with schema and write it
        sample_trade = {
            "ts": "",
            "wallet": "",
            "mint": "",
            "side": "",
            "price": 0.0,
            "size_usd": 0.0,
            "platform": "",
            "tx_hash": "",
            "pool_id": "",
            "liquidity_usd": None,
            "volume_24h_usd": None,
            "spread_bps": None,
            "honeypot_pass": None,
            "wallet_roi_30d_pct": None,
            "wallet_winrate_30d": None,
            "wallet_trades_30d": None,
            "extra": None,
        }
        con.register("trades_view", [sample_trade])
        sql = f"COPY (SELECT * FROM trades_view LIMIT 0) TO '{output_path}' (FORMAT 'parquet')"

    con.execute(sql)
    return 0


def main() -> int:
    """Main entry point for the ingest_history CLI tool."""
    parser = argparse.ArgumentParser(
        description="Ingest raw history data and normalize to Parquet."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV/Parquet file",
    )
    parser.add_argument(
        "--format",
        default="dune",
        help="Format specifier (default: dune)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to output Parquet file",
    )
    args = parser.parse_args()

    # Step 1: Read source records
    records = iter_source_records(args.input, args.format)

    # Step 2: Normalize and filter invalid records
    valid_trades = normalize_and_filter(records)

    # Step 3: Write to Parquet sorted by timestamp
    write_parquet(valid_trades, args.out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
