from __future__ import annotations
import json, hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

def _key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(row.get("chain", "")),
        str(row.get("env", "")),
        str(row.get("entity_type", "")),
        str(row.get("entity_id", "")),
    )

def merge_snapshot_dir(snapshot_dir: Path) -> List[Dict[str, Any]]:
    """Load one datagatherer snapshot directory into normalized feature rows."""
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    chain = manifest.get("chain")
    env = manifest.get("env")
    generated_at = manifest.get("generated_at")
    rows_out: List[Dict[str, Any]] = []
    for g in manifest.get("gatherers", []):
        name = g["name"]
        file = snapshot_dir / g["file"]
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                r.setdefault("chain", chain)
                r.setdefault("env", env)
                r.setdefault("_gatherer", name)
                r.setdefault("_asof", generated_at)
                rows_out.append(r)
    return rows_out

def build_feature_db(snapshot_dirs: Iterable[Path], out_dir: Path) -> Dict[str, Any]:
    """Create a replicable feature DB: one JSONL per entity_type, last-write-wins by _asof."""
    out_dir.mkdir(parents=True, exist_ok=True)
    latest: Dict[Tuple[str,str,str,str], Dict[str, Any]] = {}
    for sd in snapshot_dirs:
        for r in merge_snapshot_dir(sd):
            k = _key(r)
            prev = latest.get(k)
            if prev is None or str(r.get("_asof","")) >= str(prev.get("_asof","")):
                latest[k] = r

    by_entity: Dict[str, List[Dict[str, Any]]] = {}
    for r in latest.values():
        et = str(r.get("entity_type","unknown"))
        by_entity.setdefault(et, []).append(r)

    manifest: Dict[str, Any] = {"entities": [], "rows_total": len(latest)}
    for et, rows in by_entity.items():
        rows.sort(key=lambda x: (x.get("chain",""), x.get("env",""), x.get("entity_id","")))
        fn = out_dir / f"{et}.jsonl"
        with fn.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        sha = hashlib.sha256(fn.read_bytes()).hexdigest()
        manifest["entities"].append({"entity_type": et, "rows": len(rows), "file": fn.name, "sha256": sha})

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
