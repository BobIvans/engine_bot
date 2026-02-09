#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, List
from gmee.entity_maps import EntityMap

def read_jsonl(p: Path) -> List[Dict[str, Any]]:
    rows=[]
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def write_jsonl(p: Path, rows: List[Dict[str, Any]]) -> None:
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="feature_db entity_type jsonl (or any jsonl)")
    ap.add_argument("--map", dest="map_path", required=True, help="entity map yaml")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    em = EntityMap.load(args.map_path)
    rows = read_jsonl(Path(args.inp))
    out = em.enrich(rows)
    write_jsonl(Path(args.out), out)
    print(args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
