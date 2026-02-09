#!/usr/bin/env python3
from __future__ import annotations

"""Capture RAW provider responses into reproducible JSONL snapshots.

This is P0-safe: it writes only to local filesystem under --out-dir.

Input format (JSONL): each line is either:
  A) {"observed_ts": "...", "request": {...}, "response": {...}, ...}
  B) any JSON object (we will store it under response)

We store:
  - provider_id, license_tag, plan
  - observed_ts, ingested_ts
  - request/response
  - response_sha256
  - optional source_ref (trace_id/trade_id/attempt_id) to anchor provider data to your trace scope
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is importable when running as a script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.capture import RawRecord, RawSnapshotWriter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, help="provider_id (e.g. nansen, kaiko)")
    ap.add_argument("--license-tag", required=True, help="license/tag string to keep ToS provenance")
    ap.add_argument("--plan", default="trial", help="plan name")
    ap.add_argument("--input", required=True, help="path to JSONL input")
    ap.add_argument("--out-dir", default="out/capture", help="output root directory")
    ap.add_argument("--snapshot-id", default=None, help="optional snapshot_id override")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    writer = RawSnapshotWriter(
        args.out_dir,
        provider_id=args.provider,
        license_tag=args.license_tag,
        plan=args.plan,
        snapshot_id=args.snapshot_id,
    )

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)

            observed_ts = obj.get("observed_ts") or obj.get("ts") or obj.get("timestamp")
            if observed_ts is None:
                # If provider payload has no timestamp, you can still capture it,
                # but normalization will need an anchor later.
                observed_ts = "1970-01-01T00:00:00.000Z"

            request = obj.get("request")
            response = obj.get("response") if isinstance(obj, dict) and "response" in obj else obj

            source_ref = obj.get("source_ref")
            http_status = obj.get("http_status")
            rate_limit_bucket = obj.get("rate_limit_bucket")

            writer.append(
                RawRecord(
                    provider_id=args.provider,
                    license_tag=args.license_tag,
                    plan=args.plan,
                    observed_ts=str(observed_ts),
                    request=request,
                    response=response,
                    http_status=http_status,
                    rate_limit_bucket=rate_limit_bucket,
                    source_ref=source_ref,
                )
            )

    meta = writer.finalize()
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
