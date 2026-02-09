from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .clickhouse import ClickHouseQueryRunner
from .evidence import export_trace_evidence_bundle, export_trade_evidence_bundle, verify_bundle_integrity
from .report_html import render_bundle_report
from .capture.glue import (
    load_snapshots,
    match_snapshots_for_trade,
    attach_snapshots_via_forensics,
    write_capture_refs_jsonl,
    write_external_snapshot_paths_json,
    copy_snapshot_manifests,
)
from .models import WriterContext


def _parse_ch_datetime64_utc(s: str) -> datetime:
    # ClickHouse JSONEachRow returns DateTime64 as 'YYYY-mm-dd HH:MM:SS.sss'
    s2 = str(s).strip()
    if not s2:
        return datetime.now(timezone.utc)
    if " " in s2 and "T" not in s2:
        s2 = s2.replace(" ", "T")
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

@dataclass(frozen=True)
class InvestigationResult:
    out_dir: Path
    trace_id: Optional[str]
    report_html: Optional[Path]

def resolve_trace_id(ch: ClickHouseQueryRunner, trade_id: str, database: Optional[str] = None) -> Optional[str]:
    # Primary: trades
    sqls = [
        ("trades", "SELECT trace_id FROM trades WHERE trade_id = {trade_id:UUID} LIMIT 1"),
        ("trade_attempts", "SELECT trace_id FROM trade_attempts WHERE trade_id = {trade_id:UUID} LIMIT 1"),
        ("rpc_events", "SELECT trace_id FROM rpc_events WHERE trade_id = {trade_id:UUID} LIMIT 1"),
        ("microticks_1s", "SELECT trace_id FROM microticks_1s WHERE trade_id = {trade_id:UUID} LIMIT 1"),
        ("signals_raw", "SELECT trace_id FROM signals_raw WHERE trade_id = {trade_id:UUID} LIMIT 1"),
    ]
    for _, sql in sqls:
        try:
            rows = ch.query_json(sql, params={"trade_id": trade_id}, database=database)
            if rows and rows[0].get("trace_id"):
                return rows[0]["trace_id"]
        except Exception:
            continue
    return None

def investigate_trade_id(
    ch: ClickHouseQueryRunner,
    trade_id: str,
    out_root: Path = Path("out/investigations"),
    database: Optional[str] = None,
    render_report: bool = True,
    verify: bool = True,
    force_trace_scope: bool = True,
    *,
    capture_root: Optional[str | Path] = None,
    attach_capture_refs: bool = True,
    copy_capture_manifests: bool = True,
    capture_slack_seconds: int = 0,
) -> InvestigationResult:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_root / f"trade_{trade_id}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = resolve_trace_id(ch, trade_id=trade_id, database=database)

    # Prefer trace-scope bundle if we can resolve trace_id.
    if trace_id and force_trace_scope:
        export_trace_evidence_bundle(ch, trace_id=trace_id, out_dir=out_dir, database=database)
    else:
        export_trade_evidence_bundle(ch, trade_id=trade_id, out_dir=out_dir, database=database)

    if verify:
        verify_bundle_integrity(out_dir)

    report = None
    if render_report:
        report = render_bundle_report(out_dir)

    return InvestigationResult(out_dir=out_dir, trace_id=trace_id, report_html=report)
