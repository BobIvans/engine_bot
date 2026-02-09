#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.evidence import export_trade_evidence_bundle, export_trace_evidence_bundle


def main() -> int:
    ap = argparse.ArgumentParser(description="Export GMEE P0 evidence bundle (trade-scope or trace-scope).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--trade-id", help="Trade UUID")
    g.add_argument("--trace-id", help="Trace UUID")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--no-forensics", action="store_true", help="Do not include forensics_events")
    args = ap.parse_args()

    runner = ClickHouseQueryRunner.from_env()
    include_forensics = not args.no_forensics

    if args.trade_id:
        export_trade_evidence_bundle(runner, UUID(args.trade_id), Path(args.out), include_forensics=include_forensics)
    else:
        export_trace_evidence_bundle(runner, UUID(args.trace_id), Path(args.out), include_forensics=include_forensics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
