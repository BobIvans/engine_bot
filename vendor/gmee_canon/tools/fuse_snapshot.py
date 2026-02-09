#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from gmee.fusion import fuse_snapshot

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-prefix", action="store_true")
    args = ap.parse_args()
    sd = Path(args.snapshot_dir)
    out = Path(args.out) if args.out else (sd / "fused_features.jsonl")
    manifest = fuse_snapshot(sd, out, prefix_by_gatherer=not args.no_prefix)
    print(json.dumps(manifest, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
