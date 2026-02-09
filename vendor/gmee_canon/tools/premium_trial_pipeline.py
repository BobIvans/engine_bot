#!/usr/bin/env python3
from __future__ import annotations

"""One-command pipeline for short premium-access windows.

It converts a trial/demo window into long-lived reproducible artifacts:
  1) RAW snapshot (JSONL with metadata + hashes)
  2) Universal Variables (UV) normalized via provider mapping YAML
  3) Trade-derived labels (optional; from ClickHouse)
  4) Snapshot manifest (SHA256 pinned)

It DOES NOT call provider APIs itself (ToS-safe). You pass exported responses.

Example:
  python tools/premium_trial_pipeline.py \
    --provider nansen_like \
    --license-tag nansen_trial_2025Q1 \
    --plan trial \
    --input responses.jsonl \
    --mapping configs/providers/mappings/example_provider.yaml \
    --snapshot-id trial_nansen_2025Q1_day1 \
    --since 2025-01-01T00:00:00.000Z --until 2025-01-02T00:00:00.000Z
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.capture import ProviderMapping, RawRecord, RawSnapshotWriter, SnapshotBuilder, TradeLabelsExporter, UniversalVarsWriter
from gmee.clickhouse import ClickHouseQueryRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True)
    ap.add_argument("--license-tag", required=True)
    ap.add_argument("--plan", default="trial")
    ap.add_argument("--input", required=True, help="JSONL of exported provider responses")
    ap.add_argument("--mapping", required=True, help="provider mapping YAML")
    ap.add_argument("--out-dir", default="out/capture")
    ap.add_argument("--snapshot-id", required=True, help="stable snapshot id (keep forever)")
    ap.add_argument("--since", default=None, help="optional label export start ts")
    ap.add_argument("--until", default=None, help="optional label export end ts")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    # 1) RAW capture
    raw_writer = RawSnapshotWriter(
        out_dir,
        provider_id=args.provider,
        license_tag=args.license_tag,
        plan=args.plan,
        snapshot_id=args.snapshot_id,
    )

    import json as _json

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = _json.loads(line)
            observed_ts = obj.get("observed_ts") or obj.get("ts") or obj.get("timestamp") or "1970-01-01T00:00:00.000Z"
            request = obj.get("request")
            response = obj.get("response") if isinstance(obj, dict) and "response" in obj else obj

            raw_writer.append(
                RawRecord(
                    provider_id=args.provider,
                    license_tag=args.license_tag,
                    plan=args.plan,
                    observed_ts=str(observed_ts),
                    request=request,
                    response=response,
                    http_status=obj.get("http_status"),
                    rate_limit_bucket=obj.get("rate_limit_bucket"),
                    source_ref=obj.get("source_ref"),
                )
            )

    raw_meta = raw_writer.finalize()

    # 2) Normalize to Universal Variables
    mapping = ProviderMapping.from_yaml(args.mapping)
    uv_writer = UniversalVarsWriter(out_dir, provider_id=args.provider, snapshot_id=args.snapshot_id)

    raw_path = Path(raw_meta["raw_path"])
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = _json.loads(line)
            uv_writer.append_many(mapping.normalize_one(row))
    uv_meta = uv_writer.finalize()

    labels_path = None
    if args.since and args.until:
        # 3) Labels from ClickHouse (your execution truth)
        runner = ClickHouseQueryRunner.from_env()
        exp = TradeLabelsExporter(runner, out_dir)
        labels = exp.derive_labels(since=args.since, until=args.until, snapshot_id=args.snapshot_id)
        labels_path = str(exp.write_jsonl(snapshot_id=args.snapshot_id, labels=labels))

    # 4) Snapshot manifest
    sb = SnapshotBuilder(out_dir, args.snapshot_id)
    provider_id = args.provider
    raw_dir = out_dir / "raw" / provider_id / args.snapshot_id
    uv_dir = out_dir / "uv" / provider_id / args.snapshot_id
    sb.add_provider(provider_id=provider_id, license_tag=args.license_tag, plan=args.plan, raw_meta_path=raw_dir / "raw_meta.json")
    sb.add_file(raw_dir / "raw.jsonl", kind="raw", provider_id=provider_id)
    sb.add_file(raw_dir / "raw_meta.json", kind="raw_meta", provider_id=provider_id)
    sb.add_file(uv_dir / "uv.jsonl", kind="uv", provider_id=provider_id)
    sb.add_file(uv_dir / "uv_meta.json", kind="uv_meta", provider_id=provider_id)
    if labels_path:
        sb.add_file(Path(labels_path), kind="labels")
    manifest_path = sb.write(notes=args.notes)

    print(
        json.dumps(
            {
                "snapshot_id": args.snapshot_id,
                "raw": raw_meta,
                "uv": uv_meta,
                "labels_path": labels_path,
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
