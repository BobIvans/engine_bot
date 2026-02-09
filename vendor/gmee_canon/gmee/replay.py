from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import UUID

from .clickhouse import ClickHouseQueryRunner
from .evidence import verify_bundle_integrity


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows



def _is_trace_bundle_dir(p: Path) -> bool:
    return (p / "trace_manifest.json").exists()


def _delete_existing_for_table(
    runner: ClickHouseQueryRunner,
    table: str,
    *,
    trade_id: UUID,
    trace_id: Optional[UUID],
    sample_row: Mapping[str, Any],
) -> None:
    """DELETE rows for a table using trade_id or trace_id if present in the row schema.

    Uses synchronous mutations to make --force deterministic in CI/tests.
    """
    if "trade_id" in sample_row and trade_id.int != 0:
        runner.execute_raw(
            f"ALTER TABLE {table} DELETE WHERE trade_id={{trade_id:UUID}}",
            params={"trade_id": str(trade_id)},
            settings={"mutations_sync": "2"},
        )
        return
    if trace_id and ("trace_id" in sample_row):
        runner.execute_raw(
            f"ALTER TABLE {table} DELETE WHERE trace_id={{trace_id:UUID}}",
            params={"trace_id": str(trace_id)},
            settings={"mutations_sync": "2"},
        )
        return


def _safe_count_for_skip_existing(
    runner: ClickHouseQueryRunner,
    sql: str,
    params: Mapping[str, Any],
) -> int:
    try:
        return _safe_count_for_skip_existing(runner, sql, params)
    except Exception:
        return 0


def replay_trade_evidence_bundle(
    runner: ClickHouseQueryRunner,
    bundle_dir: str | Path,
    *,
    skip_existing: bool = True,
    force: bool = False,
    verify_hashes: bool = True,
) -> None:
    """Replay an evidence bundle into ClickHouse with strict Tier-0 ordering.

    Note: this is a *data* replayer, not a semantic writer — it preserves rows exactly.
    """
    b = Path(bundle_dir)
    if verify_hashes:
        verify_bundle_integrity(b)

    manifest = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    trade_id = UUID(manifest["trade_id"])
    trace_id = UUID(manifest["trace_id"]) if manifest.get("trace_id") else None

    if force:
        # --force implies we should not skip; we will delete rows and then insert the bundle.
        skip_existing = False


    # Helper counts for skip_existing
    if skip_existing and trace_id:
        c = _safe_count_for_skip_existing(runner, "SELECT count() FROM signals_raw WHERE trace_id={trace_id:UUID}", {"trace_id": str(trace_id)})
        if c == 0:
            rows = _read_jsonl(b / "signals_raw.jsonl")
            if rows:
                if force:
                    _delete_existing_for_table(runner, "signals_raw", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
                runner.insert_json_each_row("signals_raw", rows)
    elif not skip_existing:
        rows = _read_jsonl(b / "signals_raw.jsonl")
        if rows:
            runner.insert_json_each_row("signals_raw", rows)

    # trade_attempts (idempotent by token)
    rows = _read_jsonl(b / "trade_attempts.jsonl")
    if rows:
        if force:
            _delete_existing_for_table(runner, "trade_attempts", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
        runner.insert_json_each_row_idempotent_token("trade_attempts", rows, token_field="idempotency_token")

    # rpc_events (idempotent by token)
    rows = _read_jsonl(b / "rpc_events.jsonl")
    if rows:
        if force:
            _delete_existing_for_table(runner, "rpc_events", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
        runner.insert_json_each_row_idempotent_token("rpc_events", rows, token_field="idempotency_token")

    # trades (insert-if-not-exists by trade_id)
    rows = _read_jsonl(b / "trades.jsonl")
    if rows:
        if force:
            _delete_existing_for_table(runner, "trades", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
        exists = _safe_count_for_skip_existing(runner, "SELECT count() FROM trades WHERE trade_id={trade_id:UUID}", {"trade_id": str(trade_id)})
        if (exists == 0) or (not skip_existing):
            # Single row lifecycle
            runner.insert_json_each_row("trades", rows)

    # microticks_1s (skip if any exist for trade_id)
    rows = _read_jsonl(b / "microticks_1s.jsonl")
    if rows:
        if force:
            _delete_existing_for_table(runner, "microticks_1s", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
        exists = _safe_count_for_skip_existing(runner, "SELECT count() FROM microticks_1s WHERE trade_id={trade_id:UUID}", {"trade_id": str(trade_id)})
        if (exists == 0) or (not skip_existing):
            runner.insert_json_each_row("microticks_1s", rows)

    # forensics_events (skip if any exist for trade_id/trace_id)
    rows = _read_jsonl(b / "forensics_events.jsonl")
    if rows:
        if force:
            _delete_existing_for_table(runner, "forensics_events", trade_id=trade_id, trace_id=trace_id, sample_row=rows[0])
        if trace_id:
            exists = _safe_count_for_skip_existing(runner, 
                "SELECT count() FROM forensics_events WHERE (trade_id={trade_id:UUID}) OR (trace_id={trace_id:UUID})",
                {"trade_id": str(trade_id), "trace_id": str(trace_id)},
            )
        else:
            exists = _safe_count_for_skip_existing(runner, "SELECT count() FROM forensics_events WHERE trade_id={trade_id:UUID}", {"trade_id": str(trade_id)})
        if (exists == 0) or (not skip_existing):
            runner.insert_json_each_row("forensics_events", rows)


def replay_trace_evidence_bundle(
    runner: ClickHouseQueryRunner,
    bundle_dir: str | Path,
    *,
    skip_existing: bool = True,
    force: bool = False,
    verify_hashes: bool = True,
) -> None:
    """Replay a trace-scope bundle (produced by export_trace_evidence_bundle)."""
    b = Path(bundle_dir)
    manifest = json.loads((b / "trace_manifest.json").read_text(encoding="utf-8"))

    trace_id = UUID(manifest["trace_id"])
    if force:
        skip_existing = False

    # Replay trace-level signals_raw first (if present)
    sig_path = b / "trace_signals_raw.jsonl"
    rows = _read_jsonl(sig_path)
    if rows:
        if force:
            _delete_existing_for_table(runner, "signals_raw", trade_id=UUID(int=0), trace_id=trace_id, sample_row=rows[0])
        if skip_existing:
            exists = _safe_count_for_skip_existing(
                runner,
                "SELECT count() FROM signals_raw WHERE trace_id={trace_id:UUID}",
                {"trace_id": str(trace_id)},
            )
            if exists == 0:
                runner.insert_json_each_row("signals_raw", rows)
        else:
            runner.insert_json_each_row("signals_raw", rows)

    # Replay trace-level forensics (if present)
    fe_path = b / "trace_forensics_events.jsonl"
    rows = _read_jsonl(fe_path)
    if rows:
        if force:
            _delete_existing_for_table(runner, "forensics_events", trade_id=UUID(int=0), trace_id=trace_id, sample_row=rows[0])
        if skip_existing:
            exists = _safe_count_for_skip_existing(
                runner,
                "SELECT count() FROM forensics_events WHERE trace_id={trace_id:UUID}",
                {"trace_id": str(trace_id)},
            )
            if exists == 0:
                runner.insert_json_each_row("forensics_events", rows)
        else:
            runner.insert_json_each_row("forensics_events", rows)

    # Replay per-trade bundles
    trade_ids = manifest.get("trade_ids", [])
    for tid in trade_ids:
        td = b / "trades" / tid
        replay_trade_evidence_bundle(
            runner,
            td,
            skip_existing=skip_existing,
            force=force,
            verify_hashes=verify_hashes,
        )


def replay_any_evidence_bundle(
    runner: ClickHouseQueryRunner,
    bundle_dir: str | Path,
    *,
    skip_existing: bool = True,
    force: bool = False,
    verify_hashes: bool = True,
) -> None:
    """Replay a trade-scope or trace-scope bundle (auto-detect)."""
    b = Path(bundle_dir)
    if _is_trace_bundle_dir(b):
        replay_trace_evidence_bundle(runner, b, skip_existing=skip_existing, force=force, verify_hashes=verify_hashes)
    else:
        replay_trade_evidence_bundle(runner, b, skip_existing=skip_existing, force=force, verify_hashes=verify_hashes)
