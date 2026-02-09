#!/usr/bin/env python3
from __future__ import annotations

"""Export trade-derived labels from ClickHouse into JSONL artifacts.

Labels are your "execution truth" and are designed to be correlated with
provider Universal Variables later, even if the provider access expires.

P0-safe: writes only to filesystem under --out-dir.

Example:
  CLICKHOUSE_HTTP_URL=http://localhost:8123 \
  python tools/export_trade_labels.py --since 2025-01-01T00:00:00.000Z --until 2025-01-02T00:00:00.000Z \
    --snapshot-id trial_20250101 --out-dir out/capture
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.capture import TradeLabelsExporter
from gmee.clickhouse import ClickHouseQueryRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="start time (ISO, UTC)")
    ap.add_argument("--until", required=True, help="end time (ISO, UTC)")
    ap.add_argument("--snapshot-id", required=True, help="snapshot id to tag labels")
    ap.add_argument("--out-dir", default="out/capture", help="output root")
    args = ap.parse_args()

    runner = ClickHouseQueryRunner.from_env()
    exp = TradeLabelsExporter(runner, args.out_dir)
    labels = exp.derive_labels(since=args.since, until=args.until, snapshot_id=args.snapshot_id)
    out_path = exp.write_jsonl(snapshot_id=args.snapshot_id, labels=labels)
    print(json.dumps({"labels_path": str(out_path), "labels": len(list(labels)) if False else len(labels)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
