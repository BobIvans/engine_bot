from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import UUID

from .clickhouse import ClickHouseQueryRunner
from .attrs import extract_attribute_counts
from .config import REPO_ROOT


@dataclass(frozen=True)
class EvidenceFile:
    table: str
    filename: str
    row_count: int
    sha256: str


@dataclass(frozen=True)
class EvidenceManifest:
    version: str
    exported_at_utc: str
    trade_id: str
    trace_id: Optional[str]
    chain: Optional[str]
    env: Optional[str]
    clickhouse_database: str
    files: list[EvidenceFile]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "exported_at_utc": self.exported_at_utc,
            "trade_id": self.trade_id,
            "trace_id": self.trace_id,
            "chain": self.chain,
            "env": self.env,
            "clickhouse_database": self.clickhouse_database,
            "files": [
                {
                    "table": f.table,
                    "filename": f.filename,
                    "row_count": f.row_count,
                    "sha256": f.sha256,
                }
                for f in self.files
            ],
        }


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    # Normalize to stable JSON (sort_keys) to avoid non-deterministic key ordering.
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _write_attributes(out_dir: Path, *, signals_path: Path, forensics_path: Path, filename: str) -> None:
    """Non-canonical helper: harvest JSON attributes for new data variables (payload/details)."""
    payloads: list[str] = []
    details: list[str] = []
    if signals_path.exists():
        for line in signals_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pj = obj.get("payload_json")
                if pj:
                    payloads.append(str(pj))
            except Exception:
                continue
    if forensics_path.exists():
        for line in forensics_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                dj = obj.get("details_json")
                if dj:
                    details.append(str(dj))
            except Exception:
                continue

    key_counts, value_counts = extract_attribute_counts(payloads + details)
    top_keys = [k for k, _ in key_counts.most_common(200)]
    out = {
        "top_keys": top_keys,
        "key_counts": {k: int(key_counts[k]) for k in top_keys},
        "top_values": {k: dict(value_counts.get(k, {}).most_common(10)) for k in top_keys},
    }
    (out_dir / filename).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

def _select_one_json(runner: ClickHouseQueryRunner, sql: str, params: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    rows = runner.select_json_each_row_typed(sql, params)
    return rows[0] if rows else None


def export_trade_evidence_bundle(
    runner: ClickHouseQueryRunner,
    trade_id: UUID | str,
    out_dir: str | Path,
    *,
    include_forensics: bool = True,
) -> Path:
    """Export a deterministic evidence bundle for a single trade_id.

    Does NOT modify canonical SQL/YAML/DDL. Uses ad-hoc SELECTs only.
    """
    tid = UUID(str(trade_id))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Derive trace_id/chain/env from trades or trade_attempts (whichever exists).
    meta = (
        _select_one_json(
            runner,
            "SELECT trace_id, chain, env FROM trades WHERE trade_id={trade_id:UUID} LIMIT 1 FORMAT JSONEachRow",
            {"trade_id": str(tid)},
        )
        or _select_one_json(
            runner,
            "SELECT trace_id, chain, env FROM trade_attempts WHERE trade_id={trade_id:UUID} LIMIT 1 FORMAT JSONEachRow",
            {"trade_id": str(tid)},
        )
        or {}
    )
    trace_id = meta.get("trace_id")
    chain = meta.get("chain")
    env = meta.get("env")

    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    files: list[EvidenceFile] = []

    # 1) signals_raw by trace_id (if known)
    if trace_id:
        rows = runner.select_json_each_row_typed(
            "SELECT * FROM signals_raw WHERE trace_id={trace_id:UUID} ORDER BY signal_time, signal_id FORMAT JSONEachRow",
            {"trace_id": str(UUID(str(trace_id)))},
        )
    else:
        rows = []
    fn = "signals_raw.jsonl"
    _write_jsonl(out / fn, rows)
    files.append(EvidenceFile("signals_raw", fn, len(rows), _sha256_file(out / fn)))

    # 2) trade_attempts by trade_id
    rows = runner.select_json_each_row_typed(
        "SELECT * FROM trade_attempts WHERE trade_id={trade_id:UUID} ORDER BY local_send_time, attempt_no, attempt_id FORMAT JSONEachRow",
        {"trade_id": str(tid)},
    )
    fn = "trade_attempts.jsonl"
    _write_jsonl(out / fn, rows)
    files.append(EvidenceFile("trade_attempts", fn, len(rows), _sha256_file(out / fn)))

    # 3) rpc_events by trade_id
    rows = runner.select_json_each_row_typed(
        "SELECT * FROM rpc_events WHERE trade_id={trade_id:UUID} ORDER BY sent_ts, rpc_arm, attempt_id FORMAT JSONEachRow",
        {"trade_id": str(tid)},
    )
    fn = "rpc_events.jsonl"
    _write_jsonl(out / fn, rows)
    files.append(EvidenceFile("rpc_events", fn, len(rows), _sha256_file(out / fn)))

    # 4) trades row by trade_id
    rows = runner.select_json_each_row_typed(
        "SELECT * FROM trades WHERE trade_id={trade_id:UUID} LIMIT 1 FORMAT JSONEachRow",
        {"trade_id": str(tid)},
    )
    fn = "trades.jsonl"
    _write_jsonl(out / fn, rows)
    files.append(EvidenceFile("trades", fn, len(rows), _sha256_file(out / fn)))

    # 5) microticks by trade_id
    rows = runner.select_json_each_row_typed(
        "SELECT * FROM microticks_1s WHERE trade_id={trade_id:UUID} ORDER BY t_offset_s FORMAT JSONEachRow",
        {"trade_id": str(tid)},
    )
    fn = "microticks_1s.jsonl"
    _write_jsonl(out / fn, rows)
    files.append(EvidenceFile("microticks_1s", fn, len(rows), _sha256_file(out / fn)))

    # 6) forensics (optional) by trade_id/trace_id
    if include_forensics:
        if trace_id:
            rows = runner.select_json_each_row_typed(
                "SELECT * FROM forensics_events WHERE (trade_id={trade_id:UUID}) OR (trace_id={trace_id:UUID}) ORDER BY ts, kind, severity FORMAT JSONEachRow",
                {"trade_id": str(tid), "trace_id": str(UUID(str(trace_id)))},
            )
        else:
            rows = runner.select_json_each_row_typed(
                "SELECT * FROM forensics_events WHERE (trade_id={trade_id:UUID}) ORDER BY ts, kind, severity FORMAT JSONEachRow",
                {"trade_id": str(tid)},
            )
        fn = "forensics_events.jsonl"
        _write_jsonl(out / fn, rows)
        files.append(EvidenceFile("forensics_events", fn, len(rows), _sha256_file(out / fn)))

    manifest = EvidenceManifest(
        version="p0-evidence-bundle-v1",
        exported_at_utc=exported_at,
        trade_id=str(tid),
        trace_id=str(trace_id) if trace_id else None,
        chain=str(chain) if chain else None,
        env=str(env) if env else None,
        clickhouse_database=runner.database,
        files=files,
    )
    (out / "manifest.json").write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    # Non-canonical: harvest generic attributes from JSON payloads/details for new sources
    _write_attributes(out, signals_path=out / "signals_raw.jsonl", forensics_path=out / "forensics_events.jsonl", filename="attributes.json")

    # Human helper
    (out / "README.txt").write_text(
        "GMEE P0 evidence bundle (Variant A)\n\n"
        "Files are deterministic JSONL extracts keyed by trade_id/trace_id.\n"
        "To replay into a fresh ClickHouse database, use tools/replay_evidence_bundle.py.\n",
        encoding="utf-8",
    )

    return out



# ---------------------------
# Trace-scope bundle (P0-safe)
# ---------------------------

def _describe_table_columns(runner: ClickHouseQueryRunner, table: str) -> set[str]:
    """Return set of column names for table (best-effort)."""
    try:
        out = runner.execute_raw(f"DESCRIBE TABLE {table} FORMAT JSONEachRow")
    except Exception:
        return set()
    cols: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        name = obj.get("name")
        if isinstance(name, str):
            cols.add(name)
    return cols


def _select_distinct_uuid_list(
    runner: ClickHouseQueryRunner,
    sql: str,
    params: Mapping[str, Any],
    key: str,
) -> list[str]:
    out = runner.execute_raw(sql, params=params)
    vals: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # JSONEachRow or TSV
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                v = obj.get(key)
                if isinstance(v, str):
                    vals.append(v)
            except Exception:
                continue
        else:
            vals.append(line.split("\t")[0])
    # stable unique ordering
    return sorted({v for v in vals})


def export_trace_evidence_bundle(
    runner: ClickHouseQueryRunner,
    trace_id: UUID | str,
    out_dir: str | Path,
    *,
    include_forensics: bool = True,
) -> Path:
    """Export a trace-scope bundle: one index + per-trade sub-bundles.

    Structure:
      <out_dir>/
        trace_manifest.json
        trace_signals_raw.jsonl
        trace_forensics_events.jsonl (optional)
        trades/<trade_id>/... (per-trade bundle with manifest.json)

    No canonical SQL/YAML/DDL changes; ad-hoc SELECTs only.
    """
    tid = UUID(str(trace_id))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Collect trade_ids for the trace (best-effort, schema-aware).
    trade_ids: set[str] = set()
    for table in ("trades", "trade_attempts", "rpc_events", "microticks_1s"):
        cols = _describe_table_columns(runner, table)
        if not cols or ("trace_id" not in cols) or ("trade_id" not in cols):
            continue
        ids = _select_distinct_uuid_list(
            runner,
            f"SELECT DISTINCT trade_id FROM {table} WHERE trace_id={{trace_id:UUID}} FORMAT JSONEachRow",
            {"trace_id": str(tid)},
            "trade_id",
        )
        trade_ids.update(ids)

    trade_ids_sorted = sorted(trade_ids)

    # 2) Export trace-level signals_raw (if available)
    trace_files: list[EvidenceFile] = []
    cols = _describe_table_columns(runner, "signals_raw")
    if "trace_id" in cols:
        rows = runner.select_json_each_row_typed(
            "SELECT * FROM signals_raw WHERE trace_id={trace_id:UUID} ORDER BY signal_time, signal_seq FORMAT JSONEachRow",
            {"trace_id": str(tid)},
        )
        fn = "trace_signals_raw.jsonl"
        _write_jsonl(out / fn, rows)
        trace_files.append(EvidenceFile("signals_raw", fn, len(rows), _sha256_file(out / fn)))

    # 3) Trace-level forensics
    if include_forensics:
        cols = _describe_table_columns(runner, "forensics_events")
        if "trace_id" in cols:
            rows = runner.select_json_each_row_typed(
                "SELECT * FROM forensics_events WHERE trace_id={trace_id:UUID} ORDER BY ts, kind, severity FORMAT JSONEachRow",
                {"trace_id": str(tid)},
            )
            fn = "trace_forensics_events.jsonl"
            _write_jsonl(out / fn, rows)
            trace_files.append(EvidenceFile("forensics_events", fn, len(rows), _sha256_file(out / fn)))

    # 4) Export per-trade sub-bundles
    trades_dir = out / "trades"
    trades_dir.mkdir(parents=True, exist_ok=True)
    bundles: list[dict[str, Any]] = []
    for trade_id in trade_ids_sorted:
        subdir = trades_dir / trade_id
        export_trade_evidence_bundle(runner, trade_id, subdir, include_forensics=include_forensics)
        manifest_path = subdir / "manifest.json"
        bundles.append(
            {
                "trade_id": trade_id,
                "path": f"trades/{trade_id}",
                "manifest_sha256": _sha256_file(manifest_path),
            }
        )

    # 5) Write trace manifest
    exported_at = datetime.now(timezone.utc).isoformat()
    trace_manifest = {
        "version": "p0-trace-bundle-v1",
        "exported_at_utc": exported_at,
        "trace_id": str(tid),
        "clickhouse_database": runner.database,
        "trade_ids": trade_ids_sorted,
        "trace_files": [f.to_dict() for f in trace_files],
        "trade_bundles": bundles,
    }
    (out / "trace_manifest.json").write_text(
        json.dumps(trace_manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return out

def verify_bundle_integrity(bundle_dir: str | Path) -> None:
    """Verify manifest sha256 for all files."""
    p = Path(bundle_dir)
    manifest = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    for f in manifest.get("files", []):
        fp = p / f["filename"]
        got = _sha256_file(fp)
        if got != f["sha256"]:
            raise AssertionError(f"Evidence file hash mismatch for {fp.name}: expected={f['sha256']} got={got}")
