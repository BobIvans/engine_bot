from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .clickhouse import ClickHouseQueryRunner


@dataclass
class IntegrityReport:
    scope: dict[str, str]
    missing_rpc_attempts: int
    missing_entry_attempt: int
    missing_exit_attempt: int
    missing_microticks_trade: int
    invalid_confirm_quality_rpc: int
    invalid_confirm_quality_trades: int

    def assert_ok(self) -> None:
        bad = []
        if self.missing_rpc_attempts:
            bad.append(f"rpc_events -> trade_attempts missing: {self.missing_rpc_attempts}")
        if self.missing_entry_attempt:
            bad.append(f"trades.entry_attempt_id missing in trade_attempts: {self.missing_entry_attempt}")
        if self.missing_exit_attempt:
            bad.append(f"trades.exit_attempt_id missing in trade_attempts: {self.missing_exit_attempt}")
        if self.missing_microticks_trade:
            bad.append(f"microticks_1s -> trades missing: {self.missing_microticks_trade}")
        if self.invalid_confirm_quality_rpc:
            bad.append(f"rpc_events.confirm_quality invalid: {self.invalid_confirm_quality_rpc}")
        if self.invalid_confirm_quality_trades:
            bad.append(f"trades.entry_confirm_quality invalid: {self.invalid_confirm_quality_trades}")
        if bad:
            raise RuntimeError("P0 integrity checks failed:\n - " + "\n - ".join(bad))


def _scope_clause(alias: str, trade_id: Optional[str], trace_id: Optional[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    parts: list[str] = []
    if trade_id:
        parts.append(f"AND {alias}.trade_id={{trade_id:UUID}}")
        params["trade_id"] = trade_id
    if trace_id:
        parts.append(f"AND {alias}.trace_id={{trace_id:UUID}}")
        params["trace_id"] = trace_id
    return ("\n".join(parts), params)


def check_integrity(
    runner: ClickHouseQueryRunner,
    *,
    trade_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> IntegrityReport:
    """Run referential and enum integrity checks. Use scope filters for fast CI."""
    scope = {}
    if trade_id:
        scope["trade_id"] = trade_id
    if trace_id:
        scope["trace_id"] = trace_id

    s_r, p_r = _scope_clause("r", trade_id, trace_id)
    missing_rpc_attempts = runner.select_int_typed(
        f"""
        SELECT count()
        FROM rpc_events r
        LEFT JOIN trade_attempts a ON r.attempt_id = a.attempt_id
        WHERE a.attempt_id IS NULL
        {s_r}
        """,
        p_r,
    )

    s_t, p_t = _scope_clause("t", trade_id, trace_id)
    missing_entry_attempt = runner.select_int_typed(
        f"""
        SELECT count()
        FROM trades t
        LEFT JOIN trade_attempts a ON t.entry_attempt_id = a.attempt_id
        WHERE a.attempt_id IS NULL
        {s_t}
        """,
        p_t,
    )

    missing_exit_attempt = runner.select_int_typed(
        f"""
        SELECT count()
        FROM trades t
        LEFT JOIN trade_attempts a ON t.exit_attempt_id = a.attempt_id
        WHERE t.exit_attempt_id IS NOT NULL AND a.attempt_id IS NULL
        {s_t}
        """,
        p_t,
    )

    s_m, p_m = _scope_clause("m", trade_id, trace_id)
    missing_microticks_trade = runner.select_int_typed(
        f"""
        SELECT count()
        FROM microticks_1s m
        LEFT JOIN trades t ON m.trade_id = t.trade_id
        WHERE t.trade_id IS NULL
        {s_m}
        """,
        p_m,
    )

    invalid_confirm_quality_rpc = runner.select_int_typed(
        f"""
        SELECT count()
        FROM rpc_events r
        WHERE r.confirm_quality NOT IN ('ok','suspect','reorged')
        {s_r}
        """,
        p_r,
    )
    invalid_confirm_quality_trades = runner.select_int_typed(
        f"""
        SELECT count()
        FROM trades t
        WHERE t.entry_confirm_quality NOT IN ('ok','suspect','reorged')
        {s_t}
        """,
        p_t,
    )

    return IntegrityReport(
        scope=scope,
        missing_rpc_attempts=missing_rpc_attempts,
        missing_entry_attempt=missing_entry_attempt,
        missing_exit_attempt=missing_exit_attempt,
        missing_microticks_trade=missing_microticks_trade,
        invalid_confirm_quality_rpc=invalid_confirm_quality_rpc,
        invalid_confirm_quality_trades=invalid_confirm_quality_trades,
    )
