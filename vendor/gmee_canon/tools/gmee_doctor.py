#!/usr/bin/env python3
"""GMEE P0 doctor + one-button investigations (P0-safe).

Checks (default):
- Canonical file hashes + no bytecode caches.
- ClickHouse schema applies on a clean database.
- Canary gates (seed + checks) pass.
- Oracle glue_select gate passes (TSV 1:1).
- Schema guard + referential integrity checks pass.

Investigation (optional):
- Resolve trace_id from trade_id.
- Export trace-scope evidence bundle.
- Validate bundle sha256 + row counts.
- Render deterministic HTML report.

No modifications to canonical SQL/YAML/DDL/docs/scripts.
"""

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.schema_guard import assert_p0_schema
from gmee.integrity import check_integrity
from gmee.investigate import investigate_trade_id
from ci import repo_audit
from ci import oracle_glue_select_gate


def _runner_for_db(db: str) -> ClickHouseQueryRunner:
    r = ClickHouseQueryRunner.from_env()
    r.database = db
    return r


def run_checks() -> tuple[int, str]:
    rc = repo_audit.main()
    if rc:
        print("repo audit failed")
        return 1, ""

    # Create a fresh DB per run (avoid stateful flakes).
    db = os.environ.get("CH_DATABASE") or f"gmee_doctor_{uuid.uuid4().hex[:8]}"
    print(f"[doctor] using ClickHouse database: {db}")

    # Ensure DB exists
    r0 = ClickHouseQueryRunner.from_env()
    r0.execute_raw(f"CREATE DATABASE IF NOT EXISTS {db}")

    r = _runner_for_db(db)

    # Apply schema
    r.run_sql_file("schemas/clickhouse.sql")

    # Canary gates
    r.run_sql_file("scripts/canary_golden_trace.sql")
    r.run_sql_file("scripts/canary_checks.sql")

    # Oracle gate (seed + glue_select TSV compare)
    os.environ["CH_DATABASE"] = db
    if oracle_glue_select_gate.main() != 0:
        print("oracle gate failed")
        return 1, db

    # Schema guard
    assert_p0_schema(r)

    # Referential integrity checks on oracle trade_id
    oracle_trade_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    rep = check_integrity(r, trade_id=oracle_trade_id)
    rep.assert_ok()

    print("[doctor] OK")
    return 0, db


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--investigate-trade-id", default=None, help="export evidence bundle + report for this trade_id")
    ap.add_argument("--investigate-out", default="out/investigations", help="output root directory")
    ap.add_argument("--investigate-existing-db", default=None, help="use this DB for investigation instead of doctor sandbox DB")
    ap.add_argument("--only-investigate", action="store_true", help="skip checks; only export evidence from existing DB")
    ap.add_argument("--capture-root", default="out/capture", help="root directory containing capture snapshots (default: out/capture)")
    ap.add_argument("--no-attach-capture-refs", action="store_true", help="do not write external_capture_ref forensics rows when snapshots match")
    ap.add_argument("--no-copy-capture-manifests", action="store_true", help="do not copy snapshot_manifest.json into the evidence bundle")
    ap.add_argument("--capture-slack-seconds", type=int, default=0, help="slack in seconds when matching buy_time to snapshot observed_range")
    args = ap.parse_args()

    db = ""
    if not args.only_investigate:
        rc, db = run_checks()
        if rc:
            return rc

    if args.investigate_trade_id:
        out_root = Path(args.investigate_out)
        if args.investigate_existing_db:
            r = _runner_for_db(args.investigate_existing_db)
        else:
            if not db:
                # fallback to env DB when only-investigate
                r = ClickHouseQueryRunner.from_env()
            else:
                r = _runner_for_db(db)
        res = investigate_trade_id(
            r,
            trade_id=args.investigate_trade_id,
            out_root=out_root,
            database=r.database,
            capture_root=(args.capture_root or None),
            attach_capture_refs=(not args.no_attach_capture_refs),
            copy_capture_manifests=(not args.no_copy_capture_manifests),
            capture_slack_seconds=int(args.capture_slack_seconds or 0),
        )
        print(f"[investigate] out_dir={res.out_dir}")
        if res.trace_id:
            print(f"[investigate] trace_id={res.trace_id}")
        if res.report_html:
            print(f"[investigate] report={res.report_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
