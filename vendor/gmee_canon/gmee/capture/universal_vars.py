from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml

from ..util import stable_json_dumps


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts(ts: Any) -> datetime:
    """Parse timestamps from typical provider payloads.

    Supported:
    - ISO strings with Z suffix
    - "YYYY-MM-DD HH:MM:SS(.mmm)" (assumed UTC)
    - datetime objects
    """
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc)
    if ts is None:
        raise ValueError("ts is None")
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Allow space instead of T
    if "T" not in s and " " in s and "+" not in s:
        # naive UTC
        try:
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def bucket(dt: datetime, seconds: int) -> datetime:
    epoch = int(dt.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


_SEG_RE = re.compile(r"^(?P<name>[^\[]+)(?:\[(?P<idx>\d+)\])?$")


def get_path(obj: Any, path: str) -> Any:
    """Very small path extractor.

    Path examples:
      $.response.items[0].score
      response.wallet
      observed_ts

    Notes:
    - This is intentionally NOT a full JSONPath implementation (P0-safe simplicity).
    - Use mappings with stable provider response formats.
    """
    p = path.strip()
    if p.startswith("const:"):
        return p[len("const:") :]
    if p in ("$", "$.", ""):
        return obj
    if p.startswith("$."):
        p = p[2:]
    cur = obj
    for seg in p.split("."):
        if seg == "":
            continue
        m = _SEG_RE.match(seg)
        if not m:
            raise KeyError(f"Bad path segment: {seg}")
        name = m.group("name")
        idx = m.group("idx")
        # dict lookup
        if isinstance(cur, Mapping):
            cur = cur.get(name)
        else:
            raise KeyError(f"Cannot access '{name}' on non-mapping object")
        if idx is not None:
            if isinstance(cur, list):
                i = int(idx)
                cur = cur[i] if 0 <= i < len(cur) else None
            else:
                raise KeyError(f"Expected list at '{name}' to index")
    return cur


def extract(obj: Any, spec: Any) -> Any:
    """Extract a value from obj using a spec.

    spec can be:
    - a scalar (returned as-is)
    - a string path (via get_path)
    - a list of fallbacks (first non-None)
    """
    if isinstance(spec, list):
        for s in spec:
            v = extract(obj, s)
            if v is not None:
                return v
        return None
    if isinstance(spec, str):
        # treat as path if it looks like one; else constant
        if spec.startswith("$.") or "." in spec or spec.startswith("const:"):
            return get_path(obj, spec)
        # single token: try mapping field, else constant string
        if isinstance(obj, Mapping) and spec in obj:
            return obj.get(spec)
        return spec
    return spec


def coerce(value: Any, value_type: Optional[str]) -> Any:
    if value_type is None:
        return value
    t = value_type.lower().strip()
    if value is None:
        return None
    if t in ("float", "float64", "float32"):
        return float(value)
    if t in ("int", "int64", "int32", "uint", "uint64", "uint32"):
        return int(value)
    if t in ("bool", "boolean"):
        if isinstance(value, bool):
            return value
        s = str(value).lower().strip()
        return s in ("1", "true", "t", "yes", "y")
    if t in ("str", "string"):
        return str(value)
    return value


@dataclass(frozen=True)
class UniversalVar:
    """A provider-agnostic variable record."""

    uv_id: str
    snapshot_id: str
    provider_id: str
    license_tag: str

    entity_type: str
    entity_id: str

    ts: str
    ts_bucket_1s: str
    ts_bucket_1m: str
    ts_bucket_5m: str

    var_name: str
    value: Any
    unit: str
    confidence: float

    source_ref: Mapping[str, Any]
    ingested_ts: str


class ProviderMapping:
    """YAML mapping: raw -> UniversalVar."""

    def __init__(self, provider_id: str, vars_rules: list[Mapping[str, Any]]) -> None:
        self.provider_id = provider_id
        self.vars_rules = vars_rules

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProviderMapping":
        p = Path(path)
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        provider_id = raw.get("provider_id") or raw.get("name") or p.stem
        rules = raw.get("vars") or raw.get("rules") or []
        if not isinstance(rules, list) or not rules:
            raise ValueError(f"Mapping YAML must define a non-empty vars list: {path}")
        return cls(provider_id=str(provider_id), vars_rules=list(rules))

    def normalize_one(self, raw_row: Mapping[str, Any]) -> list[UniversalVar]:
        out: list[UniversalVar] = []
        snapshot_id = str(raw_row.get("snapshot_id") or raw_row.get("_snapshot_id") or "")
        license_tag = str(raw_row.get("license_tag") or "")
        provider_id = str(raw_row.get("provider_id") or self.provider_id)

        for r in self.vars_rules:
            var_name = str(r.get("var_name") or r.get("name"))
            entity_type = str(r.get("entity_type"))
            entity_id_spec = r.get("entity_id") or r.get("entity_id_path")
            ts_spec = r.get("ts") or r.get("ts_path") or "observed_ts"
            val_spec = r.get("value") or r.get("value_path")

            if not (var_name and entity_type and entity_id_spec is not None and val_spec is not None):
                raise ValueError(f"Bad mapping rule (missing fields): {r}")

            entity_id = extract(raw_row, entity_id_spec)
            if entity_id is None:
                continue

            ts_val = extract(raw_row, ts_spec)
            if ts_val is None:
                continue
            dt = parse_ts(ts_val)

            value = extract(raw_row, val_spec)
            value = coerce(value, r.get("value_type"))
            unit = str(r.get("unit") or "")
            conf = extract(raw_row, r.get("confidence", 1.0))
            try:
                conf_f = float(conf) if conf is not None else 1.0
            except Exception:
                conf_f = 1.0

            source_ref = {
                "raw_response_sha256": raw_row.get("response_sha256"),
                "raw_path": raw_row.get("raw_path"),
                "request": raw_row.get("request"),
            }
            # carry trace/trade IDs when present
            if isinstance(raw_row.get("source_ref"), Mapping):
                source_ref["source_ref"] = dict(raw_row["source_ref"])

            out.append(
                UniversalVar(
                    uv_id=str(uuid.uuid4()),
                    snapshot_id=snapshot_id,
                    provider_id=provider_id,
                    license_tag=license_tag,
                    entity_type=str(entity_type),
                    entity_id=str(entity_id),
                    ts=iso_z(dt),
                    ts_bucket_1s=iso_z(bucket(dt, 1)),
                    ts_bucket_1m=iso_z(bucket(dt, 60)),
                    ts_bucket_5m=iso_z(bucket(dt, 300)),
                    var_name=var_name,
                    value=value,
                    unit=unit,
                    confidence=conf_f,
                    source_ref=source_ref,
                    ingested_ts=_utc_now_iso(),
                )
            )

        return out


class UniversalVarsWriter:
    """Append-only Universal Variables writer."""

    def __init__(
        self,
        out_dir: str | Path,
        *,
        provider_id: str,
        snapshot_id: str,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.provider_id = provider_id
        self.snapshot_id = snapshot_id
        self.snapshot_dir = self.out_dir / "uv" / self.provider_id / self.snapshot_id
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.uv_path = self.snapshot_dir / "uv.jsonl"
        self.meta_path = self.snapshot_dir / "uv_meta.json"
        self._count = 0
        self._min_ts: Optional[str] = None
        self._max_ts: Optional[str] = None

    def append(self, uv: UniversalVar) -> None:
        line = stable_json_dumps(asdict(uv))
        with self.uv_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._count += 1
        self._min_ts = uv.ts if self._min_ts is None else min(self._min_ts, uv.ts)
        self._max_ts = uv.ts if self._max_ts is None else max(self._max_ts, uv.ts)

    def append_many(self, uvs: Iterable[UniversalVar]) -> None:
        for u in uvs:
            self.append(u)

    def finalize(self) -> Mapping[str, Any]:
        meta = {
            "snapshot_id": self.snapshot_id,
            "provider_id": self.provider_id,
            "created_at": _utc_now_iso(),
            "records": self._count,
            "ts_range": {"min": self._min_ts, "max": self._max_ts},
            "uv_path": str(self.uv_path),
        }
        self.meta_path.write_text(stable_json_dumps(meta) + "\n", encoding="utf-8")
        return meta
