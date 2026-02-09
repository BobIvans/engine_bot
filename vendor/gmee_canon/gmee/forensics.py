from __future__ import annotations

import uuid
from typing import Any, Mapping, Optional

from .clickhouse import ClickHouseQueryRunner
from .models import WriterContext
from .util import stable_json_dumps


def emit_forensics(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: Optional[str],
    trade_id: Optional[str],
    attempt_id: Optional[str],
    kind: str,
    severity: str,
    details: Mapping[str, Any],
) -> None:
    """Append a forensics event (P0).

    Table has DEFAULT now64(3) for ts, so we omit ts for deterministic inserts.
    """
    row = {
        "event_id": str(uuid.uuid4()),
        "chain": ctx.chain,
        "env": ctx.env,
        "trace_id": trace_id,
        "trade_id": trade_id,
        "attempt_id": attempt_id,
        "kind": kind,
        "severity": severity,
        "details_json": stable_json_dumps(details),
    }
    runner.insert_json_each_row("forensics_events", [row])


def emit_time_skew(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: Optional[str],
    trade_id: Optional[str],
    attempt_id: Optional[str],
    details: Mapping[str, Any],
) -> None:
    emit_forensics(
        runner,
        ctx,
        trace_id=trace_id,
        trade_id=trade_id,
        attempt_id=attempt_id,
        kind="time_skew",
        severity="crit",
        details=details,
    )


def emit_confirm_quality(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: Optional[str],
    trade_id: Optional[str],
    attempt_id: Optional[str],
    confirm_quality: str,
    details: Mapping[str, Any],
) -> None:
    cq = confirm_quality.lower().strip()
    if cq == "suspect":
        kind, severity = "suspect_confirm", "warn"
    elif cq == "reorged":
        kind, severity = "reorg", "crit"
    else:
        return
    emit_forensics(
        runner,
        ctx,
        trace_id=trace_id,
        trade_id=trade_id,
        attempt_id=attempt_id,
        kind=kind,
        severity=severity,
        details=details,
    )


def emit_schema_mismatch(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: Optional[str],
    trade_id: Optional[str],
    attempt_id: Optional[str],
    details: Mapping[str, Any],
    severity: str = "crit",
) -> None:
    emit_forensics(
        runner,
        ctx,
        trace_id=trace_id,
        trade_id=trade_id,
        attempt_id=attempt_id,
        kind="schema_mismatch",
        severity=severity,
        details=details,
    )

def emit_ordering_violation(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: str | None,
    trade_id: str | None,
    attempt_id: str | None,
    details: Mapping[str, Any],
) -> None:
    """P0: ordering violation (prevent partial/quiet garbage)."""
    emit_forensics(
        runner,
        ctx,
        trace_id=trace_id,
        trade_id=trade_id,
        attempt_id=attempt_id,
        kind='ordering_violation',
        severity='crit',
        details=details,
    )


def emit_external_capture_ref(
    runner: ClickHouseQueryRunner,
    ctx: WriterContext,
    *,
    trace_id: str | None,
    trade_id: str | None,
    attempt_id: str | None,
    provider_id: str,
    snapshot_id: str,
    license_tag: str,
    raw_sha256: str | None = None,
    uv_sha256: str | None = None,
    severity: str = 'info',
) -> None:
    """P0-safe bridge: attach external provider snapshot provenance to a trace/trade.

    This does NOT change schemas or canonical SQL. It simply records a reference
    (provider_id, snapshot_id, license_tag, hashes) into forensics_events.details_json.
    """
    details = {
        'provider_id': provider_id,
        'snapshot_id': snapshot_id,
        'license_tag': license_tag,
        'raw_sha256': raw_sha256,
        'uv_sha256': uv_sha256,
    }
    emit_forensics(
        runner,
        ctx,
        trace_id=trace_id,
        trade_id=trade_id,
        attempt_id=attempt_id,
        kind='external_capture_ref',
        severity=severity,
        details=details,
    )

