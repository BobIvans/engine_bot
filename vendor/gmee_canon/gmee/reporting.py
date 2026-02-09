from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .clickhouse import ClickHouseQueryRunner


def trace_report(
    runner: ClickHouseQueryRunner,
    *,
    trace_id: str,
) -> dict[str, Any]:
    """Generate a deterministic trace diagnostics report (P0)."""
    report: dict[str, Any] = {"trace_id": trace_id}

    # Row counts by table
    tables = ["signals_raw", "trade_attempts", "rpc_events", "trades", "microticks_1s", "forensics_events"]
    counts: dict[str, int] = {}
    for t in tables:
        counts[t] = runner.select_int_typed(
            f"SELECT count() FROM {t} WHERE trace_id={{trace_id:UUID}}",
            {"trace_id": trace_id},
        )
    report["counts"] = counts

    # RPC quality distribution
    rpc_quality = runner.select_json_each_row_typed(
        """
        SELECT stage, confirm_quality, count() AS n
        FROM rpc_events
        WHERE trace_id={trace_id:UUID}
        GROUP BY stage, confirm_quality
        ORDER BY stage, confirm_quality
        FORMAT JSONEachRow
        """,
        {"trace_id": trace_id},
    )
    report["rpc_quality"] = rpc_quality

    # Trades planned outputs distribution (mode/aggr_flag)
    planned = runner.select_json_each_row_typed(
        """
        SELECT mode, aggr_flag, count() AS n
        FROM trades
        WHERE trace_id={trace_id:UUID}
        GROUP BY mode, aggr_flag
        ORDER BY mode, aggr_flag
        FORMAT JSONEachRow
        """,
        {"trace_id": trace_id},
    )
    report["planned_modes"] = planned

    # Latency summary per arm (p50/p95/p99)
    latency = runner.select_json_each_row_typed(
        """
        SELECT stage, rpc_arm,
               quantiles(0.5,0.95,0.99)(toFloat64OrZero(latency_ms)) AS q,
               count() AS n
        FROM rpc_events
        WHERE trace_id={trace_id:UUID}
        GROUP BY stage, rpc_arm
        ORDER BY stage, rpc_arm
        FORMAT JSONEachRow
        """,
        {"trace_id": trace_id},
    )
    report["rpc_latency_quantiles_ms"] = latency

    # Forensics summary
    forensics = runner.select_json_each_row_typed(
        """
        SELECT kind, severity, count() AS n
        FROM forensics_events
        WHERE trace_id={trace_id:UUID}
        GROUP BY kind, severity
        ORDER BY kind, severity
        FORMAT JSONEachRow
        """,
        {"trace_id": trace_id},
    )
    report["forensics_summary"] = forensics

    return report
