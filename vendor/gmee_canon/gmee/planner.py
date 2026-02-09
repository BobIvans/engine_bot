from __future__ import annotations

import uuid
from typing import Any, Mapping, Optional

from .clickhouse import ClickHouseQueryRunner
from .config import glue_select_params_from_cfg
from .models import ExitPlan


def _ch_escape_string(s: str) -> str:
    # Minimal SQL string literal escaping for P0 (single quotes + backslash).
    return s.replace("\\", "\\\\").replace("'", "\\'")


def compute_exit_plan(
    chain: str,
    trade_id: str | uuid.UUID,
    cfg: Mapping[str, Any],
    *,
    runner: Optional[ClickHouseQueryRunner] = None,
    trade_snapshot: Optional[Mapping[str, Any]] = None,
) -> ExitPlan:
    """Compute exit plan with 1:1 parity to queries/04_glue_select.sql (P0).

    P0 rule: DO NOT re-implement the math in code.
    We execute the canonical SQL and return its stable columns.

    If trade_snapshot is provided, we create a TEMPORARY table named `trades`
    (session-scoped) with the minimal columns needed by 04_glue_select:
      trade_id, chain, traced_wallet, buy_time, buy_price_usd

    This allows planning before inserting the full `trades` row, without editing SQL/DDL/YAML.
    """
    runner = runner or ClickHouseQueryRunner.from_env()

    tid = str(trade_id)
    uuid.UUID(tid)  # validate UUID

    params = glue_select_params_from_cfg(cfg, chain)
    params = {**params, "chain": chain, "trade_id": tid}

    if trade_snapshot is None:
        out = runner.execute_function("glue_select", params)
    else:
        required = {"trade_id", "chain", "traced_wallet", "buy_time", "buy_price_usd"}
        missing = required - set(trade_snapshot.keys())
        if missing:
            raise ValueError(f"trade_snapshot missing required keys: {sorted(missing)}")

        snap_trade_id = str(trade_snapshot["trade_id"])
        if snap_trade_id != tid:
            raise ValueError("trade_snapshot.trade_id must match trade_id argument")

        snap_chain = str(trade_snapshot["chain"])
        if snap_chain != chain:
            raise ValueError("trade_snapshot.chain must match chain argument")

        traced_wallet = str(trade_snapshot["traced_wallet"])
        buy_time = str(trade_snapshot["buy_time"])
        buy_price = float(trade_snapshot["buy_price_usd"])

        with runner.session(timeout_s=60) as sid:
            runner.execute_raw(
                "CREATE TEMPORARY TABLE trades (\n"
                "  trade_id UUID,\n"
                "  chain LowCardinality(String),\n"
                "  traced_wallet String,\n"
                "  buy_time DateTime64(3,'UTC'),\n"
                "  buy_price_usd Float64\n"
                ")",
                session_id=sid,
            )

            # Use ClickHouse query parameters (no manual string escaping)
            runner.execute_raw(
                "INSERT INTO trades (trade_id, chain, traced_wallet, buy_time, buy_price_usd) VALUES (\n"
                "  {trade_id:UUID},\n"
                "  {chain:String},\n"
                "  {traced_wallet:String},\n"
                "  {buy_time:DateTime64(3,'UTC')},\n"
                "  {buy_price_usd:Float64}\n"
                ")",
                session_id=sid,
                params={
                    "trade_id": tid,
                    "chain": chain,
                    "traced_wallet": traced_wallet,
                    "buy_time": buy_time,
                    "buy_price_usd": buy_price,
                },
                settings={"date_time_input_format": "best_effort"},
            )

            out = runner.execute_function("glue_select", params, session_id=sid)

    line = out.strip().splitlines()[0] if out.strip() else ""
    parts = line.split("\t")
    if len(parts) != 6:
        raise RuntimeError(f"Unexpected glue_select output: {line!r}")

    _, mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag = parts
    return ExitPlan(
        mode=mode,
        planned_hold_sec=int(planned_hold_sec),
        epsilon_ms=int(epsilon_ms),
        planned_exit_ts=planned_exit_ts,
        aggr_flag=int(aggr_flag),
    )
