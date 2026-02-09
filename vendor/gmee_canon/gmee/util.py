from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json_dumps(obj: Any) -> str:
    """Canonical JSON encoding for hashing (stable across runs)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ensure_fixed_hex64(s: str) -> str:
    """Ensure a 64-char hex string (FixedString(64) contract)."""
    s = (s or "").strip().lower()
    if len(s) == 64 and all(c in "0123456789abcdef" for c in s):
        return s
    # If it's not already valid, hash it deterministically.
    return sha256_hex(s.encode("utf-8"))


def dt_to_ch_datetime64_3(dt: datetime) -> str:
    """Format datetime as ClickHouse DateTime64(3,'UTC') string."""
    if dt.tzinfo is None:
        # Interpret naive as UTC to keep deterministic P0 behavior.
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    # milliseconds precision
    ms = int(dt.microsecond / 1000)
    return dt.replace(microsecond=ms * 1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def merge_dicts(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(a)
    out.update(b)
    return out


from pathlib import Path

def repo_root() -> Path:
    # resolves repo root by walking up from this file
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / 'configs').exists() and (p / 'schemas').exists() and (p / 'queries').exists():
            return p
    return here.parent
