from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .clickhouse import ClickHouseQueryRunner


def _norm_type(t: str) -> str:
    """Normalize ClickHouse type strings for stable comparisons."""
    # remove all whitespace
    return re.sub(r"\s+", "", t or "")


# P0 schema assertions for must-log and planner fields (do not edit DDL; validate it).
# Types are normalized (whitespace-insensitive).
REQUIRED_SCHEMA: dict[str, dict[str, str]] = {
    "signals_raw": {
        "trace_id": "UUID",
        "chain": "LowCardinality(String)",
        "env": "LowCardinality(String)",
        "signal_time": "DateTime64(3,'UTC')",
        "traced_wallet": "String",
        "token_mint": "String",
    },
    "trade_attempts": {
        "attempt_id": "UUID",
        "trade_id": "UUID",
        "trace_id": "UUID",
        "chain": "LowCardinality(String)",
        "env": "LowCardinality(String)",
        "stage": "LowCardinality(String)",
        "idempotency_token": "FixedString(64)",
        "payload_hash": "FixedString(64)",
        "local_send_time": "DateTime64(3,'UTC')",
        "attempt_no": "UInt16",
    },
    "rpc_events": {
        "attempt_id": "UUID",
        "trade_id": "UUID",
        "trace_id": "UUID",
        "chain": "LowCardinality(String)",
        "env": "LowCardinality(String)",
        "stage": "LowCardinality(String)",
        "idempotency_token": "FixedString(64)",
        "rpc_arm": "LowCardinality(String)",
        "sent_ts": "DateTime64(3,'UTC')",
        "confirm_quality": "LowCardinality(String)",
    },
    "trades": {
        "trade_id": "UUID",
        "trace_id": "UUID",
        "experiment_id": "UUID",
        "config_hash": "FixedString(64)",
        "env": "LowCardinality(String)",
        "chain": "LowCardinality(String)",
        "entry_attempt_id": "UUID",
        "entry_idempotency_token": "FixedString(64)",
        "entry_confirm_quality": "LowCardinality(String)",
        # Planner outputs (P0)
        "mode": "LowCardinality(String)",
        "planned_hold_sec": "UInt32",
        "epsilon_ms": "UInt32",
        "aggr_flag": "UInt8",
        "planned_exit_ts": "DateTime64(3,'UTC')",
    },
    "microticks_1s": {
        "trade_id": "UUID",
        "trace_id": "UUID",
        "chain": "LowCardinality(String)",
        "env": "LowCardinality(String)",
        "ts": "DateTime64(3,'UTC')",
        "price_usd": "Float64",
    },
    "forensics_events": {
        "trade_id": "UUID",
        "trace_id": "UUID",
        "chain": "LowCardinality(String)",
        "env": "LowCardinality(String)",
        "kind": "LowCardinality(String)",
        "severity": "LowCardinality(String)",
        "event_ts": "DateTime64(3,'UTC')",
        "details_json": "String",
    },
}


@dataclass
class SchemaIssue:
    table: str
    column: str
    expected_type: str | None
    actual_type: str | None
    reason: str

    def __str__(self) -> str:
        return (
            f"{self.table}.{self.column}: {self.reason} "
            f"(expected={self.expected_type!r}, actual={self.actual_type!r})"
        )


def _fetch_columns(runner: ClickHouseQueryRunner, table: str) -> dict[str, str]:
    rows = runner.select_json_each_row_typed(
        """
        SELECT name, type
        FROM system.columns
        WHERE database={db:String} AND table={table:String}
        ORDER BY name
        FORMAT JSONEachRow
        """,
        {"db": runner.database, "table": table},
    )
    return {r["name"]: r["type"] for r in rows}


def assert_p0_schema(runner: ClickHouseQueryRunner) -> None:
    """Fail-fast if schema does not match P0 must-log expectations."""
    issues: list[SchemaIssue] = []
    for table, cols in REQUIRED_SCHEMA.items():
        actual = _fetch_columns(runner, table)
        if not actual:
            issues.append(SchemaIssue(table, "*", None, None, "table missing"))
            continue
        for col, exp_type in cols.items():
            if col not in actual:
                issues.append(SchemaIssue(table, col, exp_type, None, "column missing"))
                continue
            if _norm_type(actual[col]) != _norm_type(exp_type):
                issues.append(
                    SchemaIssue(
                        table,
                        col,
                        exp_type,
                        actual[col],
                        "type mismatch",
                    )
                )

    # Deterministic view anchor: wallet_profile_30d must not be anchored on now()/today()
    # (We also keep a similar guard in runtime.py; this is a CI-friendly schema check.)
    try:
        view_create = runner.execute_raw("SHOW CREATE TABLE wallet_profile_30d")
        lowered = view_create.lower()
        if "now(" in lowered or "now64(" in lowered or "today(" in lowered:
            issues.append(
                SchemaIssue(
                    "wallet_profile_30d",
                    "*",
                    None,
                    None,
                    "view is time-anchored (now/today) -> non-deterministic",
                )
            )
    except Exception:
        # If view doesn't exist, it will already be caught by schema checks elsewhere.
        pass

    if issues:
        msg = "P0 schema guard failed:\n" + "\n".join(f" - {i}" for i in issues)
        raise RuntimeError(msg)
