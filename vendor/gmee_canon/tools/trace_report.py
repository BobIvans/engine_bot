#!/usr/bin/env python3
"""Generate a deterministic JSON trace report (counts/quality/latency/forensics)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.reporting import trace_report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-id", required=True)
    ap.add_argument("--out", default="", help="Write report JSON to a file; default prints to stdout")
    args = ap.parse_args()

    r = ClickHouseQueryRunner.from_env()
    rep = trace_report(r, trace_id=args.trace_id)
    s = json.dumps(rep, indent=2, sort_keys=True, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(s + "\n", encoding="utf-8")
    else:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
