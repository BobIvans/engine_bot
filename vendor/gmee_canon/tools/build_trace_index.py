#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import REPO_ROOT


def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic JSONL indexes for trace/trade discovery (P0-safe).")
    ap.add_argument("--since", help="Start buy_time/signal_time (DateTime64 string)", required=False)
    ap.add_argument("--until", help="End buy_time/signal_time (DateTime64 string)", required=False)
    ap.add_argument("--out", help="Output directory", default="artifacts/index")
    ap.add_argument("--limit", type=int, default=50000)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = ClickHouseQueryRunner.from_env()

    # trades index
    t_where = []
    params = {"limit": int(args.limit)}
    if args.since:
        t_where.append("buy_time >= {since:DateTime64(3)}")
        params["since"] = args.since
    if args.until:
        t_where.append("buy_time <= {until:DateTime64(3)}")
        params["until"] = args.until
    t_where_sql = ("WHERE " + " AND ".join(t_where)) if t_where else ""

    trades_sql = f"""
    SELECT
      trace_id, trade_id, chain, env, source,
      traced_wallet, token_mint, pool_id,
      toString(signal_time) AS signal_time,
      toString(buy_time) AS buy_time,
      entry_rpc_winner, entry_confirm_quality,
      mode, planned_hold_sec, epsilon_ms, toString(planned_exit_ts) AS planned_exit_ts, aggr_flag
    FROM trades
    {t_where_sql}
    ORDER BY buy_time ASC, trade_id ASC
    LIMIT {{limit:UInt32}}
    FORMAT JSONEachRow
    """
    trade_rows = runner.execute_typed(trades_sql, params)
    (out_dir / "trades_index.jsonl").write_text(trade_rows)

    # signals index (per trace)
    s_where = []
    s_params = {"limit": int(args.limit)}
    if args.since:
        s_where.append("signal_time >= {since:DateTime64(3)}")
        s_params["since"] = args.since
    if args.until:
        s_where.append("signal_time <= {until:DateTime64(3)}")
        s_params["until"] = args.until
    s_where_sql = ("WHERE " + " AND ".join(s_where)) if s_where else ""

    signals_sql = f"""
    SELECT
      trace_id, chain, env, source,
      traced_wallet, token_mint, pool_id,
      toString(min(signal_time)) AS min_signal_time,
      toString(max(signal_time)) AS max_signal_time,
      count() AS signals_count
    FROM signals_raw
    {s_where_sql}
    GROUP BY trace_id, chain, env, source, traced_wallet, token_mint, pool_id
    ORDER BY max_signal_time ASC
    LIMIT {{limit:UInt32}}
    FORMAT JSONEachRow
    """
    signal_rows = runner.execute_typed(signals_sql, s_params)
    (out_dir / "signals_index.jsonl").write_text(signal_rows)

    print(f"Wrote: {out_dir/'trades_index.jsonl'}")
    print(f"Wrote: {out_dir/'signals_index.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
