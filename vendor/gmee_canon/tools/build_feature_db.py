#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from typing import List

from gmee.feature_db import build_feature_db

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots-root", default="out/datagatherers", help="root directory with snapshot subfolders")
    ap.add_argument("--out", default="out/feature_db", help="output feature_db directory")
    args = ap.parse_args()

    root = Path(args.snapshots_root)
    if not root.exists():
        raise SystemExit(f"Snapshots root not found: {root}")

    snapshot_dirs: List[Path] = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()]
    snapshot_dirs.sort()

    manifest = build_feature_db(snapshot_dirs, Path(args.out))
    print(Path(args.out))
    print(f"rows_total={manifest['rows_total']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
