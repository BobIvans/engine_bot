from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..clickhouse import ClickHouseQueryRunner
from ..util import stable_json_dumps


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except Exception:
        return None


def _cq_ok(v: Any) -> bool:
    return str(v or "").lower().strip() == "ok"


@dataclass(frozen=True)
class TradeLabel:
    """Trade-derived label (truth from your execution, not from providers)."""

    label_id: str
    trade_id: str
    trace_id: str
    chain: str
    env: str
    buy_time: str

    # Core labels
    label_success: bool
    profit_bps: Optional[float]
    slippage_bps: Optional[float]
    latency_ms: Optional[int]
    confirm_quality_entry: str
    confirm_quality_exit: str
    exclude_from_training: bool

    # Optional debug payload
    details: Mapping[str, Any]
    ingested_ts: str


class TradeLabelsExporter:
    """Export labels from ClickHouse trades table into JSONL artifacts."""

    def __init__(self, runner: ClickHouseQueryRunner, out_dir: str | Path) -> None:
        self.runner = runner
        self.out_dir = Path(out_dir)

    def _fetch_trades(self, *, since: str, until: str, limit: int = 100000) -> list[Mapping[str, Any]]:
        sql = """
        SELECT
          trade_id,
          trace_id,
          chain,
          env,
          toString(buy_time) AS buy_time,
          success_bool,
          roi,
          slippage_pct,
          entry_latency_ms,
          entry_confirm_quality,
          ifNull(exit_confirm_quality,'') AS exit_confirm_quality,
          failure_mode,
          hold_seconds
        FROM trades
        WHERE buy_time >= {since:DateTime64(3)} AND buy_time < {until:DateTime64(3)}
        ORDER BY buy_time
        LIMIT {lim:UInt32}
        FORMAT JSONEachRow
        """
        body = self.runner.execute_raw(sql, params={"since": since, "until": until, "lim": limit})
        rows: list[Mapping[str, Any]] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            import json

            rows.append(json.loads(line))
        return rows

    def derive_labels(self, *, since: str, until: str, snapshot_id: str) -> list[TradeLabel]:
        rows = self._fetch_trades(since=since, until=until)
        out: list[TradeLabel] = []
        for r in rows:
            trade_id = str(r.get("trade_id"))
            trace_id = str(r.get("trace_id"))
            chain = str(r.get("chain"))
            env = str(r.get("env"))
            buy_time = str(r.get("buy_time"))

            success_bool = int(r.get("success_bool") or 0)
            roi = _to_float(r.get("roi"))
            slippage_pct = _to_float(r.get("slippage_pct"))
            latency_ms = _to_int(r.get("entry_latency_ms"))

            cq_entry = str(r.get("entry_confirm_quality") or "").lower()
            cq_exit = str(r.get("exit_confirm_quality") or "").lower()
            failure_mode = str(r.get("failure_mode") or "").lower()

            # Profit in bps (roi is fraction, e.g. 0.01 => 100 bps)
            profit_bps = roi * 10000.0 if roi is not None else None
            slippage_bps = slippage_pct * 10000.0 if slippage_pct is not None else None

            # Training exclusion per P0 contract
            exclude = (not _cq_ok(cq_entry)) or (cq_exit not in ("", "ok"))

            label_success = (success_bool == 1) and (failure_mode in ("none", "")) and (not exclude)

            out.append(
                TradeLabel(
                    label_id=str(uuid.uuid4()),
                    trade_id=trade_id,
                    trace_id=trace_id,
                    chain=chain,
                    env=env,
                    buy_time=buy_time,
                    label_success=label_success,
                    profit_bps=profit_bps,
                    slippage_bps=slippage_bps,
                    latency_ms=latency_ms,
                    confirm_quality_entry=cq_entry,
                    confirm_quality_exit=cq_exit,
                    exclude_from_training=exclude,
                    details={
                        "snapshot_id": snapshot_id,
                        "success_bool": success_bool,
                        "failure_mode": failure_mode,
                        "hold_seconds": r.get("hold_seconds"),
                    },
                    ingested_ts=_utc_now_iso(),
                )
            )
        return out

    def write_jsonl(self, *, snapshot_id: str, labels: Iterable[TradeLabel]) -> Path:
        out_dir = self.out_dir / "labels" / snapshot_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "trade_labels.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for lab in labels:
                f.write(stable_json_dumps(asdict(lab)) + "\n")
        return path
