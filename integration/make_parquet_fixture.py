#!/usr/bin/env python3
"""integration/make_parquet_fixture.py

Utility to generate a small deterministic Parquet fixture from a CSV fixture.

We avoid committing binary Parquet files into the repo, but still want a
deterministic Parquet replay path in CI.

Usage:
  python3 -m integration.make_parquet_fixture \
    --input-csv integration/fixtures/trades.sample.csv \
    --output-parquet /tmp/trades.sample.parquet

Requires: duckdb (already in requirements.txt)
"""

from __future__ import annotations

import argparse

import duckdb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-csv", required=True)
    ap.add_argument("--output-parquet", required=True)
    args = ap.parse_args()

    con = duckdb.connect(database=":memory:")

    def _sql_lit(path: str) -> str:
        # Safe for CI fixtures: escape single quotes for SQL literal.
        return "'" + path.replace("'", "''") + "'"

    in_lit = _sql_lit(args.input_csv)
    out_lit = _sql_lit(args.output_parquet)

    sql = (
        f"COPY (SELECT * FROM read_csv_auto({in_lit}, header=true)) "
        f"TO {out_lit} (FORMAT 'parquet')"
    )
    con.execute(sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
