#!/usr/bin/env python3
"""One-button investigation: trade_id -> trace bundle -> validate -> HTML report."""
from __future__ import annotations
import argparse, os
from pathlib import Path
from gmee.clickhouse import ClickHouseQueryRunner
from gmee.investigate import investigate_trade_id

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-id", required=True)
    ap.add_argument("--out", default="out/investigations")
    ap.add_argument("--db", default=os.environ.get("CH_DATABASE"))
    ap.add_argument("--capture-root", default="out/capture")
    ap.add_argument("--no-attach-capture-refs", action="store_true")
    ap.add_argument("--no-copy-capture-manifests", action="store_true")
    ap.add_argument("--capture-slack-seconds", type=int, default=0)

    args = ap.parse_args()
    r = ClickHouseQueryRunner.from_env()
    if args.db:
        r.database = args.db
    res = investigate_trade_id(
        r,
        trade_id=args.trade_id,
        out_root=Path(args.out),
        database=r.database,
        capture_root=(args.capture_root or None),
        attach_capture_refs=(not args.no_attach_capture_refs),
        copy_capture_manifests=(not args.no_copy_capture_manifests),
        capture_slack_seconds=int(args.capture_slack_seconds or 0),
    )
    print(str(res.out_dir))
    if res.report_html:
        print(str(res.report_html))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
