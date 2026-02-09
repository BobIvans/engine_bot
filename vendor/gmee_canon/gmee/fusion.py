from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

def load_snapshot(snapshot_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    m = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    gathered: Dict[str, List[Dict[str, Any]]] = {}
    for g in m.get("gatherers", []):
        name = g["name"]
        fn = snapshot_dir / g["file"]
        rows=[]
        with fn.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        gathered[name]=rows
    return gathered

def fuse_snapshot(snapshot_dir: Path, out_file: Path, prefix_by_gatherer: bool = True) -> Dict[str, Any]:
    """Fuse all gatherer rows by (chain, env, entity_type, entity_id)."""
    gathered = load_snapshot(snapshot_dir)
    fused: Dict[Tuple[str,str,str,str], Dict[str, Any]] = {}
    for gname, rows in gathered.items():
        for r in rows:
            k=(str(r.get("chain","")), str(r.get("env","")), str(r.get("entity_type","")), str(r.get("entity_id","")))
            base=fused.get(k)
            if base is None:
                base={"chain":k[0],"env":k[1],"entity_type":k[2],"entity_id":k[3]}
                fused[k]=base
            for kk,vv in r.items():
                if kk in ("chain","env","entity_type","entity_id"):
                    continue
                out_k = f"{gname}.{kk}" if prefix_by_gatherer else kk
                if out_k not in base:
                    base[out_k]=vv

    out_rows = list(fused.values())
    out_rows.sort(key=lambda r:(r.get("entity_type",""), r.get("entity_id","")))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"rows": len(out_rows), "file": str(out_file)}
