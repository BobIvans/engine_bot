from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..util import stable_json_dumps


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    return sha256_bytes(stable_json_dumps(obj).encode("utf-8"))


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class RawRecord:
    """One captured provider response (RAW snapshot row).

    This is intentionally permissive; it can store arbitrary provider JSON.
    """

    provider_id: str
    license_tag: str
    plan: str
    observed_ts: str
    response: Any
    request: Optional[Any] = None
    http_status: Optional[int] = None
    rate_limit_bucket: Optional[str] = None
    source_ref: Optional[Mapping[str, str]] = None  # may include trace_id/trade_id/attempt_id
    ingested_ts: str = ""  # filled on write
    response_sha256: str = ""  # filled on write

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        if not row.get("ingested_ts"):
            row["ingested_ts"] = _utc_now_iso()
        if not row.get("response_sha256"):
            row["response_sha256"] = sha256_json(self.response)
        return row


class RawSnapshotWriter:
    """Append-only RAW snapshot writer.

    Output layout:
      <out_dir>/raw/<provider_id>/<snapshot_id>/raw.jsonl
      <out_dir>/raw/<provider_id>/<snapshot_id>/raw_meta.json

    No schema changes required.
    """

    def __init__(
        self,
        out_dir: str | Path,
        *,
        provider_id: str,
        license_tag: str,
        plan: str,
        snapshot_id: Optional[str] = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.provider_id = provider_id
        self.license_tag = license_tag
        self.plan = plan
        self.snapshot_id = snapshot_id or self._default_snapshot_id()

        self.snapshot_dir = self.out_dir / "raw" / self.provider_id / self.snapshot_id
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.snapshot_dir / "raw.jsonl"
        self.meta_path = self.snapshot_dir / "raw_meta.json"
        self._count = 0
        self._min_observed: Optional[str] = None
        self._max_observed: Optional[str] = None

    def _default_snapshot_id(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{ts}_{self.provider_id}_{uuid.uuid4().hex[:8]}"

    def append(self, record: RawRecord) -> None:
        row = record.to_row()
        # Embed snapshot context to make downstream normalization/replay deterministic.
        row["snapshot_id"] = self.snapshot_id
        row["raw_path"] = str(self.raw_path)
        line = stable_json_dumps(row)
        with self.raw_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._count += 1
        obs = row.get("observed_ts")
        if isinstance(obs, str):
            self._min_observed = obs if self._min_observed is None else min(self._min_observed, obs)
            self._max_observed = obs if self._max_observed is None else max(self._max_observed, obs)

    def append_many(self, records: Iterable[RawRecord]) -> None:
        for r in records:
            self.append(r)

    def finalize(self) -> dict[str, Any]:
        """Write raw_meta.json and return it."""
        meta = {
            "snapshot_id": self.snapshot_id,
            "provider_id": self.provider_id,
            "license_tag": self.license_tag,
            "plan": self.plan,
            "created_at": _utc_now_iso(),
            "records": self._count,
            "observed_range": {"min": self._min_observed, "max": self._max_observed},
            "raw_path": str(self.raw_path),
        }
        if self.raw_path.exists():
            meta["raw_sha256"] = _file_sha256(self.raw_path)
            meta["raw_bytes"] = self.raw_path.stat().st_size
        self.meta_path.write_text(stable_json_dumps(meta) + "\n", encoding="utf-8")
        return meta
