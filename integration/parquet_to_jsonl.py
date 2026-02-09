#!/usr/bin/env python3
"""integration/parquet_to_jsonl.py

P0.2 helper: convert a Parquet dataset (Data-track output) into the same JSONL format
consumed by integration/paper_pipeline.py.

This is intentionally a thin bridge so the bot-track can replay history without
requiring realtime ingestion yet.

Default required columns:
  ts, wallet, mint, side, price, size_usd, platform, tx_hash

If your Parquet uses different column names, use --colmap-json to provide a mapping
of target->source column names, e.g.:
  {"ts":"block_ts","wallet":"trader"}

Requires: duckdb (see requirements.txt)
"""

from __future__ import annotations

import argparse
import json

from integration.parquet_io import ParquetReadConfig, iter_parquet_records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input Parquet file or glob")
    ap.add_argument("--output", required=True, help="Output JSONL path")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument(
        "--colmap-json",
        default="",
        help="Optional JSON mapping of target_col -> source_col for renames",
    )
    args = ap.parse_args()

    colmap = None
    if args.colmap_json:
        colmap = json.loads(args.colmap_json)
        if not isinstance(colmap, dict):
            raise SystemExit("--colmap-json must be a JSON object")

    cfg = ParquetReadConfig(
        path=args.input,
        limit=args.limit,
        batch_size=args.batch_size,
        colmap=colmap,
    )

    n = 0
    with open(args.output, "w", encoding="utf-8") as f:
        for rec in iter_parquet_records(cfg):
            # Keep it as JSON-compatible primitives.
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1

    print(f"[ok] wrote {n} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
