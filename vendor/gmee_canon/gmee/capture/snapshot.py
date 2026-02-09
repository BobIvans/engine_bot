from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..util import stable_json_dumps


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    n = 0
    with path.open("rb") as f:
        for _ in f:
            n += 1
    return n


def infer_range_from_meta(meta_path: Path, key: str) -> Optional[Mapping[str, Any]]:
    if not meta_path.exists():
        return None
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        if key in raw:
            return raw.get(key)
    except Exception:
        pass
    return None


def default_snapshot_id(prefix: str = "snap") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{ts}"


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    created_at: str
    observed_range: Mapping[str, Any]
    providers: list[Mapping[str, Any]]
    files: list[Mapping[str, Any]]
    notes: str


class SnapshotBuilder:
    """Build a reproducible dataset snapshot manifest.

    It only uses filesystem artifacts (raw/uv/labels) and hashes them.
    """

    def __init__(self, out_dir: str | Path, snapshot_id: str) -> None:
        self.out_dir = Path(out_dir)
        self.snapshot_id = snapshot_id
        self.files: list[Mapping[str, Any]] = []
        self.providers: list[Mapping[str, Any]] = []
        self.observed_min: Optional[str] = None
        self.observed_max: Optional[str] = None

    def add_file(self, path: Path, *, kind: str, provider_id: Optional[str] = None) -> None:
        if not path.exists():
            return
        rel = str(path)
        info = {
            "path": rel,
            "kind": kind,
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix in (".jsonl", ".tsv"):
            info["rows"] = count_lines(path)
        if provider_id:
            info["provider_id"] = provider_id
        self.files.append(info)

    def add_provider(self, *, provider_id: str, license_tag: str, plan: str, raw_meta_path: Optional[Path] = None) -> None:
        rec = {"provider_id": provider_id, "license_tag": license_tag, "plan": plan}
        if raw_meta_path and raw_meta_path.exists():
            try:
                import json

                meta = json.loads(raw_meta_path.read_text(encoding="utf-8"))
                rec.update({"raw_records": meta.get("records"), "raw_sha256": meta.get("raw_sha256")})
                rng = meta.get("observed_range") or {}
                mn, mx = rng.get("min"), rng.get("max")
                if mn:
                    self.observed_min = mn if self.observed_min is None else min(self.observed_min, mn)
                if mx:
                    self.observed_max = mx if self.observed_max is None else max(self.observed_max, mx)
            except Exception:
                pass
        self.providers.append(rec)

    def write(self, *, notes: str = "") -> Path:
        manifest_dir = self.out_dir / "snapshots" / self.snapshot_id
        manifest_dir.mkdir(parents=True, exist_ok=True)
        path = manifest_dir / "snapshot_manifest.json"
        manifest = SnapshotManifest(
            snapshot_id=self.snapshot_id,
            created_at=_utc_now_iso(),
            observed_range={"min": self.observed_min, "max": self.observed_max},
            providers=self.providers,
            files=self.files,
            notes=notes,
        )
        path.write_text(stable_json_dumps(asdict(manifest)) + "\n", encoding="utf-8")
        return path
