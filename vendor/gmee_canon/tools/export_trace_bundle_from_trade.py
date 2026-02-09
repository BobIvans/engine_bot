#!/usr/bin/env python3
"""Export a trace-scope evidence bundle given a trade_id.

Convenience wrapper:
- resolves trace_id from trades table
- calls existing trace bundle exporter

P0-safe: does not change canonical artifacts.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.evidence import export_trace_evidence_bundle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r = ClickHouseQueryRunner.from_env()

    rows = r.select_json_each_row_typed(
        """
        SELECT trace_id
        FROM trades
        WHERE trade_id={trade_id:UUID}
        LIMIT 1
        FORMAT JSONEachRow
        """,
        {"trade_id": args.trade_id},
    )
    if not rows:
        print("trace_id not found for trade_id")
        return 2

    trace_id = rows[0]["trace_id"]
    out_dir = Path(args.out).resolve()
    export_trace_evidence_bundle(r, trace_id=trace_id, out_dir=out_dir)
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
