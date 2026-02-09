#!/usr/bin/env python3
"""ingestion/pipelines/token_mapping_pipeline.py

PR-PM.4: Polymarket → Solana Token Mapping Pipeline

Orchestrates loading of Polymarket snapshots and token snapshots,
computes mappings, and exports results to parquet.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add analysis to path
sys.path.insert(0, str(Path(__file__).parent / ".."))

import duckdb

from analysis.token_mapping import (
    PolymarketSnapshot,
    TokenSnapshot,
    build_all_mappings,
    compute_mapping_stats,
)


SCHEMA_VERSION = "pm4_v1"


def load_polymarket_snapshots(path: str) -> List[PolymarketSnapshot]:
    """Load Polymarket snapshots from JSON or Parquet."""
    snapshots = []
    
    if path.endswith(".json"):
        with open(path, "r") as f:
            data = json.load(f)
            for item in data:
                snapshots.append(
                    PolymarketSnapshot(
                        id=item["id"],
                        question=item["question"],
                        category=item.get("category"),
                        end_date_unix_ms=item.get("end_date_unix_ms"),
                    )
                )
    else:
        # Parquet
        con = duckdb.connect(database=":memory:")
        result = con.execute(f"SELECT * FROM read_parquet('{path}')").fetchall()
        colnames = [d[0] for d in con.description]
        for row in result:
            item = {colnames[i]: row[i] for i in range(len(colnames))}
            snapshots.append(
                PolymarketSnapshot(
                    id=item["id"],
                    question=item["question"],
                    category=item.get("category"),
                    end_date_unix_ms=item.get("end_date_unix_ms"),
                )
            )
    
    return snapshots


def load_token_snapshots(path: str) -> List[TokenSnapshot]:
    """Load token snapshots from CSV or Parquet."""
    tokens = []
    
    if path.endswith(".csv"):
        con = duckdb.connect(database=":memory:")
        result = con.execute(f"SELECT * FROM read_csv_auto('{path}', header=true)").fetchall()
        colnames = [d[0] for d in con.description]
        for row in result:
            item = {colnames[i]: row[i] for i in range(len(colnames))}
            tokens.append(
                TokenSnapshot(
                    mint=item["mint"],
                    symbol=item["symbol"],
                    name=item["name"],
                    liquidity_usd=item.get("liquidity_usd"),
                    volume_24h_usd=item.get("volume_24h_usd"),
                )
            )
    else:
        # Parquet
        con = duckdb.connect(database=":memory:")
        result = con.execute(f"SELECT * FROM read_parquet('{path}')").fetchall()
        colnames = [d[0] for d in con.description]
        for row in result:
            item = {colnames[i]: row[i] for i in range(len(colnames))}
            tokens.append(
                TokenSnapshot(
                    mint=item["mint"],
                    symbol=item["symbol"],
                    name=item["name"],
                    liquidity_usd=item.get("liquidity_usd"),
                    volume_24h_usd=item.get("volume_24h_usd"),
                )
            )
    
    return tokens


def export_mappings(
    mappings: List[Any],
    output_path: str,
    ts: int
) -> None:
    """Export mappings to Parquet."""
    if not mappings:
        # Create empty file with schema
        con = duckdb.connect(database=":memory:")
        con.execute(f"""
            CREATE TABLE mappings (
                market_id VARCHAR,
                token_mint VARCHAR,
                token_symbol VARCHAR,
                relevance_score DOUBLE,
                mapping_type VARCHAR,
                matched_keywords VARCHAR[],
                ts BIGINT,
                schema_version VARCHAR
            )
        """)
        con.execute(f"COPY mappings TO '{output_path}' (FORMAT 'parquet')")
        return
    
    # Convert to records
    records = []
    for m in mappings:
        records.append({
            "market_id": m.market_id,
            "token_mint": m.token_mint,
            "token_symbol": m.token_symbol,
            "relevance_score": m.relevance_score,
            "mapping_type": m.mapping_type,
            "matched_keywords": m.matched_keywords,
            "ts": ts,
            "schema_version": SCHEMA_VERSION,
        })
    
    # Export via DuckDB
    con = duckdb.connect(database=":memory:")
    
    # Create temp table from records
    con.execute("CREATE TABLE temp_mappings AS SELECT * FROM (VALUES) WHERE 1=0")
    for record in records:
        placeholders = ", ".join([f"?" for _ in range(len(record))])
        con.execute(
            f"INSERT INTO temp_mappings VALUES ({placeholders})",
            list(record.values())
        )
    
    # Copy to output
    con.execute(f"COPY temp_mappings TO '{output_path}' (FORMAT 'parquet')")


def run(
    polymarket_path: str,
    tokens_path: str,
    output_path: str,
    dry_run: bool = False,
    summary_json: bool = False,
) -> Dict[str, Any]:
    """
    Run the token mapping pipeline.
    
    Args:
        polymarket_path: Path to Polymarket snapshots (JSON or Parquet)
        tokens_path: Path to token snapshots (CSV or Parquet)
        output_path: Path for output Parquet
        dry_run: If True, don't write output
        summary_json: If True, output summary as JSON to stdout
    
    Returns:
        Summary dict with mapping statistics
    """
    ts = int(time.time() * 1000)
    
    # Load data
    markets = load_polymarket_snapshots(polymarket_path)
    tokens = load_token_snapshots(tokens_path)
    
    # Build mappings
    mappings = build_all_mappings(markets, tokens)
    
    # Compute stats
    stats = compute_mapping_stats(mappings)
    stats["ts"] = ts
    stats["schema_version"] = SCHEMA_VERSION
    
    # Export if not dry run
    if not dry_run:
        export_mappings(mappings, output_path, ts)
        print(f"[token_mapping] exported {len(mappings)} mappings to {output_path}", file=sys.stderr)
    
    # Output summary
    if summary_json:
        print(json.dumps(stats))
    
    return stats


def main() -> int:
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Polymarket Token Mapping Pipeline")
    parser.add_argument("--input-polymarket", required=True, help="Path to Polymarket snapshots")
    parser.add_argument("--input-tokens", required=True, help="Path to token snapshots")
    parser.add_argument("--output", required=True, help="Output Parquet path")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--summary-json", action="store_true", help="Output summary JSON to stdout")
    
    args = parser.parse_args()
    
    try:
        stats = run(
            polymarket_path=args.input_polymarket,
            tokens_path=args.input_tokens,
            output_path=args.output,
            dry_run=args.dry_run,
            summary_json=args.summary_json,
        )
        return 0
    except Exception as e:
        print(f"[token_mapping] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
