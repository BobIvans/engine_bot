from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..clickhouse import ClickHouseQueryRunner
from ..forensics import emit_external_capture_ref
from ..models import WriterContext


def _parse_iso_utc(s: str) -> datetime:
    """Parse ISO-ish timestamps (assumed UTC).

    Accepts:
      - 2025-01-01T00:00:00Z
      - 2025-01-01T00:00:00.123+00:00
      - 2025-01-01 00:00:00.123   (ClickHouse-ish)
    """
    s2 = str(s).strip()
    if not s2:
        raise ValueError("empty datetime")
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    if " " in s2 and "T" not in s2:
        s2 = s2.replace(" ", "T")
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def discover_snapshot_manifests(capture_root: str | Path) -> list[Path]:
    root = Path(capture_root)
    if not root.exists():
        return []
    return sorted(root.glob("snapshots/*/snapshot_manifest.json"))


def _load_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha_for(manifest: Mapping[str, Any], *, provider_id: str, kind: str) -> Optional[str]:
    for f in (manifest.get("files") or []):
        if f.get("kind") == kind and f.get("provider_id") == provider_id:
            return f.get("sha256")
    return None


@dataclass(frozen=True)
class CaptureProviderRef:
    provider_id: str
    license_tag: str
    plan: str
    raw_sha256: Optional[str]
    uv_sha256: Optional[str]


@dataclass(frozen=True)
class CaptureSnapshotRef:
    snapshot_id: str
    manifest_path: Path
    observed_min: Optional[datetime]
    observed_max: Optional[datetime]
    providers: list[CaptureProviderRef]
    files: list[Mapping[str, Any]]  # from manifest["files"], used for paths rendering


def load_snapshots(capture_root: str | Path) -> list[CaptureSnapshotRef]:
    snaps: list[CaptureSnapshotRef] = []
    for p in discover_snapshot_manifests(capture_root):
        try:
            m = _load_json(p)
        except Exception:
            continue

        snap_id = str(m.get("snapshot_id") or p.parent.name)
        rng = m.get("observed_range") or {}
        mn = rng.get("min")
        mx = rng.get("max")

        observed_min = _parse_iso_utc(mn) if isinstance(mn, str) and mn else None
        observed_max = _parse_iso_utc(mx) if isinstance(mx, str) and mx else None

        files = list(m.get("files") or [])
        providers: list[CaptureProviderRef] = []
        for pr in (m.get("providers") or []):
            pid = str(pr.get("provider_id") or "").strip()
            if not pid:
                continue

            uv_sha = (
                _file_sha_for(m, provider_id=pid, kind="uv_meta")
                or _file_sha_for(m, provider_id=pid, kind="uv")
            )
            providers.append(
                CaptureProviderRef(
                    provider_id=pid,
                    license_tag=str(pr.get("license_tag") or ""),
                    plan=str(pr.get("plan") or ""),
                    raw_sha256=pr.get("raw_sha256"),
                    uv_sha256=uv_sha,
                )
            )

        snaps.append(
            CaptureSnapshotRef(
                snapshot_id=snap_id,
                manifest_path=p,
                observed_min=observed_min,
                observed_max=observed_max,
                providers=providers,
                files=files,
            )
        )
    return snaps


def match_snapshots_for_trade(
    snapshots: Iterable[CaptureSnapshotRef],
    *,
    buy_time_utc: datetime,
    slack_seconds: int = 0,
) -> list[CaptureSnapshotRef]:
    """Pick snapshots whose observed_range covers buy_time (optionally with slack).

    Missing ranges are skipped by default (avoid accidental linkage).
    """
    bt = buy_time_utc.astimezone(timezone.utc)
    out: list[CaptureSnapshotRef] = []
    for s in snapshots:
        if not (s.observed_min and s.observed_max):
            continue
        mn = s.observed_min
        mx = s.observed_max
        if slack_seconds:
            mn = mn - timedelta(seconds=int(slack_seconds))
            mx = mx + timedelta(seconds=int(slack_seconds))
        if mn <= bt <= mx:
            out.append(s)
    return out


def attach_snapshots_via_forensics(
    runner: ClickHouseQueryRunner,
    *,
    ctx: WriterContext,
    trace_id: str,
    trade_id: str,
    attempt_id: Optional[str],
    snapshots: Iterable[CaptureSnapshotRef],
) -> int:
    """Emit external_capture_ref forensics rows (one per provider, per snapshot)."""
    n = 0
    for s in snapshots:
        for pr in s.providers:
            emit_external_capture_ref(
                runner,
                ctx,
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=attempt_id,
                provider_id=pr.provider_id,
                snapshot_id=s.snapshot_id,
                license_tag=pr.license_tag,
                raw_sha256=pr.raw_sha256,
                uv_sha256=pr.uv_sha256,
                severity="info",
            )
            n += 1
    return n


def write_capture_refs_jsonl(
    bundle_dir: Path,
    *,
    trade_id: str,
    trace_id: str,
    buy_time_utc: datetime,
    snapshots: Iterable[CaptureSnapshotRef],
) -> Path:
    """Bundle-local index of matched snapshots (offline-friendly)."""
    out = bundle_dir / "capture_refs.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for s in snapshots:
            rec = {
                "trade_id": trade_id,
                "trace_id": trace_id,
                "buy_time_utc": buy_time_utc.isoformat().replace("+00:00", "Z"),
                "snapshot_id": s.snapshot_id,
                "manifest_path": str(s.manifest_path),
                "observed_range": {
                    "min": s.observed_min.isoformat().replace("+00:00", "Z") if s.observed_min else None,
                    "max": s.observed_max.isoformat().replace("+00:00", "Z") if s.observed_max else None,
                },
                "providers": [
                    {
                        "provider_id": pr.provider_id,
                        "license_tag": pr.license_tag,
                        "plan": pr.plan,
                        "raw_sha256": pr.raw_sha256,
                        "uv_sha256": pr.uv_sha256,
                    }
                    for pr in s.providers
                ],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out


def write_external_snapshot_paths_json(
    bundle_dir: Path,
    *,
    capture_root: str | Path,
    snapshots: Iterable[CaptureSnapshotRef],
) -> Path:
    """Write a small paths file referencing the original RAW/UV/LABELS files.

    The evidence bundle stays small; the snapshot manifests are pinned by sha256
    and the referenced files can be re-opened locally when investigating.
    """
    out = bundle_dir / "external_snapshot_paths.json"
    base = str(Path(capture_root).resolve())
    rec = {
        "capture_root": base,
        "snapshots": [
            {
                "snapshot_id": s.snapshot_id,
                "manifest_path": str(s.manifest_path),
                "files": [
                    {
                        "path": str(f.get("path")),
                        "kind": f.get("kind"),
                        "provider_id": f.get("provider_id"),
                        "sha256": f.get("sha256"),
                        "rows": f.get("rows"),
                        "bytes": f.get("bytes"),
                    }
                    for f in (s.files or [])
                ],
            }
            for s in snapshots
        ],
    }
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def copy_snapshot_manifests(bundle_dir: Path, snapshots: Iterable[CaptureSnapshotRef]) -> int:
    """Copy snapshot_manifest.json into the evidence bundle (offline-friendly).

    Does NOT copy raw/uv payload files by default (keeps bundle small).
    """
    n = 0
    root = bundle_dir / "external_snapshots"
    for s in snapshots:
        dst = root / s.snapshot_id
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "snapshot_manifest.json").write_text(
            s.manifest_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        n += 1
    return n
