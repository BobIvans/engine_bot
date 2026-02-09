#!/usr/bin/env python3
from __future__ import annotations

"""integration/write_trade_reject.py

Writes per-trade reject events into ClickHouse for queryable debugging.

We use the existing forensics_events table:
- kind = 'trade_reject'
- trace_id = run_trace_id (pipeline invariant)

details_json is a JSON string with (minimum):
  stage: 'normalizer' | 'gates'
  reason: reject reason (enum-only)
  lineno: int|null
  wallet: str|null
  mint: str|null
  side: str|null
  tx_hash: str|null
  detail: str|null

Dry-run behaviour: print the would-insert row to stderr.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from integration.ch_client import ClickHouseConfig, make_runner
from integration.reject_reasons import assert_reason_known


def _utc_now_iso_ms() -> str:
    dt = datetime.now(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def insert_trade_reject(
    *,
    runner,
    chain: str,
    env: str,
    trace_id: str,
    stage: str,
    reason: str,
    lineno: Optional[int] = None,
    wallet: Optional[str] = None,
    mint: Optional[str] = None,
    side: Optional[str] = None,
    tx_hash: Optional[str] = None,
    detail: Optional[str] = None,
    severity: str = "info",
    dry_run: bool = False,
) -> Dict[str, Any]:
    assert_reason_known(reason)

    row: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "ts": _utc_now_iso_ms(),
        "chain": chain,
        "env": env,
        "kind": "trade_reject",
        "severity": severity,
        "trace_id": trace_id,
        "trade_id": tx_hash or None,
        "details_json": json.dumps(
            {
                "stage": stage,
                "reason": reason,
                "lineno": lineno,
                "wallet": wallet,
                "mint": mint,
                "side": side,
                "tx_hash": tx_hash,
                "detail": detail,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }

    if dry_run:
        print(f"[dry-run] would insert trade_reject: {row}", file=sys.stderr)
        return row

    runner.insert_json_each_row("forensics_events", [row])
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Insert a single trade_reject event into ClickHouse.")
    ap.add_argument("--clickhouse-url", default=None)
    ap.add_argument("--clickhouse-user", default=None)
    ap.add_argument("--clickhouse-password", default=None)
    ap.add_argument("--chain", default="solana")
    ap.add_argument("--env", default="local")
    ap.add_argument("--trace-id", required=True)
    ap.add_argument("--stage", required=True, choices=["normalizer", "gates"])
    ap.add_argument("--reason", required=True)
    ap.add_argument("--lineno", type=int, default=None)
    ap.add_argument("--wallet", default=None)
    ap.add_argument("--mint", default=None)
    ap.add_argument("--side", default=None)
    ap.add_argument("--tx-hash", default=None)
    ap.add_argument("--detail", default=None)
    ap.add_argument("--severity", default="info")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        cfg = ClickHouseConfig.from_args(args.clickhouse_url, args.clickhouse_user, args.clickhouse_password)
        runner = make_runner(cfg)
        insert_trade_reject(
            runner=runner,
            chain=args.chain,
            env=args.env,
            trace_id=args.trace_id,
            stage=args.stage,
            reason=args.reason,
            lineno=args.lineno,
            wallet=args.wallet,
            mint=args.mint,
            side=args.side,
            tx_hash=args.tx_hash,
            detail=args.detail,
            severity=args.severity,
            dry_run=args.dry_run,
        )
        return 0
    except AssertionError as e:
        print(f"BAD_INPUT: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"INTERNAL: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
