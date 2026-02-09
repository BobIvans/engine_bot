#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.discovery import discover_trades


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover trades/traces with generic filters (P0-safe).")
    ap.add_argument("--since", required=False, help="buy_time >= since (DateTime64 string)")
    ap.add_argument("--until", required=False, help="buy_time <= until (DateTime64 string)")
    ap.add_argument("--where", action="append", default=[], help="Filters: key=value, payload.<k>=v, details.<k>=v")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--json", action="store_true", help="Output JSON lines")
    args = ap.parse_args()

    runner = ClickHouseQueryRunner.from_env()
    results = discover_trades(runner, since=args.since, until=args.until, where=args.where, limit=args.limit)

    if args.json:
        for r in results:
            print(json.dumps(r.__dict__, sort_keys=True))
    else:
        for r in results:
            print(f"{r.buy_time or ''}\t{r.trade_id}\t{r.trace_id}\t{r.chain}\t{r.env}\t{r.source}\t{r.traced_wallet or ''}\t{r.token_mint or ''}\t{r.pool_id or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
