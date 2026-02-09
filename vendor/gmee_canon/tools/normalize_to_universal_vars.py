#!/usr/bin/env python3
from __future__ import annotations

"""Normalize RAW provider snapshots into Universal Variables (UV).

P0-safe: outputs are filesystem artifacts under --out-dir.

Usage:
  python tools/normalize_to_universal_vars.py \
    --mapping configs/providers/mappings/example_provider.yaml \
    --raw out/capture/raw/<provider>/<snapshot>/raw.jsonl \
    --out-dir out/capture
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.capture import ProviderMapping, UniversalVarsWriter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True, help="path to provider mapping yaml")
    ap.add_argument("--raw", required=True, help="path to raw.jsonl")
    ap.add_argument("--out-dir", default="out/capture", help="output root")
    ap.add_argument("--snapshot-id", default=None, help="override snapshot_id")
    args = ap.parse_args()

    mapping = ProviderMapping.from_yaml(args.mapping)
    raw_path = Path(args.raw)
    if not raw_path.exists():
        raise SystemExit(f"raw.jsonl not found: {raw_path}")

    # Infer snapshot/provider from the first line
    first = None
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                first = json.loads(line)
                break
    if not first:
        raise SystemExit("raw.jsonl is empty")

    snapshot_id = args.snapshot_id or str(first.get("snapshot_id") or "")
    provider_id = str(first.get("provider_id") or mapping.provider_id)
    if not snapshot_id:
        raise SystemExit("snapshot_id missing in raw rows; re-capture RAW with tools/capture_raw_snapshot.py")

    uv_writer = UniversalVarsWriter(args.out_dir, provider_id=provider_id, snapshot_id=snapshot_id)

    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            uvs = mapping.normalize_one(row)
            uv_writer.append_many(uvs)

    meta = uv_writer.finalize()
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
