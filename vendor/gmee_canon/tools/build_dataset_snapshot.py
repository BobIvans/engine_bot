#!/usr/bin/env python3
from __future__ import annotations

"""Build snapshot_manifest.json for a capture session.

The manifest is what makes a 24–72h provider trial valuable forever:
it pins files by SHA256, records provider/license provenance, and defines
observed time range.

P0-safe: filesystem only.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.capture import SnapshotBuilder


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--out-dir", default="out/capture")
    ap.add_argument("--provider", action="append", default=[], help="provider_id to include (repeatable)")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    sb = SnapshotBuilder(out_dir, args.snapshot_id)

    # Collect common artifacts:
    # raw/<provider>/<snapshot_id>/raw.jsonl + raw_meta.json
    # uv/<provider>/<snapshot_id>/uv.jsonl + uv_meta.json
    for provider_id in args.provider:
        raw_dir = out_dir / "raw" / provider_id / args.snapshot_id
        uv_dir = out_dir / "uv" / provider_id / args.snapshot_id

        raw_path = raw_dir / "raw.jsonl"
        raw_meta = raw_dir / "raw_meta.json"
        uv_path = uv_dir / "uv.jsonl"
        uv_meta = uv_dir / "uv_meta.json"

        # Provider provenance
        license_tag = ""
        plan = ""
        if raw_meta.exists():
            try:
                meta = json.loads(raw_meta.read_text(encoding="utf-8"))
                license_tag = str(meta.get("license_tag") or "")
                plan = str(meta.get("plan") or "")
            except Exception:
                pass
        sb.add_provider(provider_id=provider_id, license_tag=license_tag, plan=plan, raw_meta_path=raw_meta)

        sb.add_file(raw_path, kind="raw", provider_id=provider_id)
        sb.add_file(raw_meta, kind="raw_meta", provider_id=provider_id)
        sb.add_file(uv_path, kind="uv", provider_id=provider_id)
        sb.add_file(uv_meta, kind="uv_meta", provider_id=provider_id)

    # Labels are snapshot-scoped (not provider-scoped)
    labels_path = out_dir / "labels" / args.snapshot_id / "trade_labels.jsonl"
    if labels_path.exists():
        sb.add_file(labels_path, kind="labels")

    manifest_path = sb.write(notes=args.notes)
    print(json.dumps({"manifest": str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
