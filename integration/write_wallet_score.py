#!/usr/bin/env python3
"""integration/write_wallet_score.py

Writes a mini-ML (or heuristic) wallet score snapshot into CANON table forensics_events.

Contract (Iteration-1):
- mini-ML only produces score + features, stored as forensics_events(kind='wallet_score')
- no changes to CANON SQL/DDL; no online learning in P0

Example:
  python integration/write_wallet_score.py --traced-wallet <WALLET> --score 0.73 \
    --features-json '{"winrate_30d":0.62,"trades_30d":41}'

"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from integration.allowlist_loader import load_allowlist  # type: ignore
from integration.ch_client import ClickHouseConfig, make_runner  # type: ignore


def _utc_now_iso_ms() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _load_json_arg(json_str: Optional[str], json_file: Optional[str], default: Dict[str, Any]) -> Dict[str, Any]:
    if json_str and json_file:
        raise SystemExit("Provide only one of --features-json or --features-file")
    if json_file:
        p = Path(json_file)
        return json.loads(p.read_text(encoding="utf-8"))
    if json_str:
        return json.loads(json_str)
    return default


def _mk_allowlist_version_row(ts: str, chain: str, env: str, path: str, wallets_count: int, allowlist_hash: str) -> Dict[str, Any]:
    details = {
        "path": path,
        "wallets_count": wallets_count,
        "allowlist_hash": allowlist_hash,
    }
    return {
        "event_id": str(uuid.uuid4()),
        "ts": ts,
        "chain": chain,
        "env": env,
        "kind": "allowlist_version",
        "severity": "info",
        "details_json": json.dumps(details, ensure_ascii=False, separators=(",", ":")),
        "trace_id": None,
        "trade_id": None,
        "attempt_id": None,
    }


def insert_wallet_score(
    *,
    cfg: ClickHouseConfig,
    chain: str,
    env: str,
    traced_wallet: str,
    score: float,
    features: Dict[str, Any],
    ts: str,
    trace_id: str = "",
    trade_id: str = "",
    attempt_id: str = "",
    allowlist_path: str = "",
    log_allowlist_version: bool = True,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    allowlist_row: Optional[Dict[str, Any]] = None
    allowlist_hash: Optional[str] = None

    details: Dict[str, Any] = {
        "traced_wallet": traced_wallet.strip(),
        "score": float(score),
        "features": features,
    }

    if allowlist_path:
        wallets, allowlist_hash = load_allowlist(allowlist_path)
        details["allowlist_hash"] = allowlist_hash
        if log_allowlist_version:
            allowlist_row = _mk_allowlist_version_row(
                ts=ts,
                chain=chain,
                env=env,
                path=allowlist_path,
                wallets_count=len(wallets),
                allowlist_hash=allowlist_hash,
            )

    severity = "info" if float(score) >= 0.5 else "warn"

    row = {
        "event_id": str(uuid.uuid4()),
        "ts": ts,
        "chain": chain,
        "env": env,
        "kind": "wallet_score",
        "severity": severity,
        "details_json": json.dumps(details, ensure_ascii=False, separators=(",", ":")),
        "trace_id": trace_id or None,
        "trade_id": trade_id or None,
        "attempt_id": attempt_id or None,
    }

    if dry_run:
        print("[dry-run] would insert forensics_events(kind=wallet_score):", file=sys.stderr)
        print(json.dumps(row, ensure_ascii=False, indent=2), file=sys.stderr)
        if allowlist_row:
            print(
                "[dry-run] would also insert forensics_events(kind=allowlist_version):",
                file=sys.stderr,
            )
            print(json.dumps(allowlist_row, ensure_ascii=False, indent=2), file=sys.stderr)
        return row, allowlist_row

    runner = make_runner(cfg)
    if allowlist_row:
        runner.insert_json_each_row("forensics_events", [allowlist_row])
    runner.insert_json_each_row("forensics_events", [row])
    return row, allowlist_row


def main() -> None:
    ap = argparse.ArgumentParser(description="Write wallet_score event into forensics_events.")
    ap.add_argument("--ch-url", default=None, help="Override CLICKHOUSE_URL")
    ap.add_argument("--ch-user", default=None, help="Override CLICKHOUSE_USER")
    ap.add_argument("--ch-password", default=None, help="Override CLICKHOUSE_PASSWORD")

    ap.add_argument("--chain", default="solana")
    ap.add_argument("--env", default="canary")

    ap.add_argument("--traced-wallet", "--wallet", dest="traced_wallet", required=True)
    ap.add_argument("--score", required=True, type=float)

    ap.add_argument("--features-json", default=None)
    ap.add_argument("--features-file", default=None)

    ap.add_argument("--allowlist", "--allowlist-path", dest="allowlist", default="", help="Optional allowlist path to include hash in details")
    ap.add_argument("--no-log-allowlist-version", action="store_true", help="Do not write allowlist_version forensics event")

    ap.add_argument("--trace-id", default="", help="Optional trace_id correlation")
    ap.add_argument("--trade-id", default="", help="Optional trade_id correlation")
    ap.add_argument("--attempt-id", default="", help="Optional attempt_id correlation")

    ap.add_argument("--dry-run", action="store_true", help="Validate inputs and print rows, without ClickHouse writes")

    args = ap.parse_args()

    cfg = ClickHouseConfig.from_args(args.ch_url, args.ch_user, args.ch_password)
    ts = _utc_now_iso_ms()
    features = _load_json_arg(args.features_json, args.features_file, default={})

    row, _ = insert_wallet_score(
        cfg=cfg,
        chain=args.chain,
        env=args.env,
        traced_wallet=args.traced_wallet,
        score=float(args.score),
        features=features,
        ts=ts,
        trace_id=args.trace_id,
        trade_id=args.trade_id,
        attempt_id=args.attempt_id,
        allowlist_path=args.allowlist,
        log_allowlist_version=not bool(args.no_log_allowlist_version),
        dry_run=bool(args.dry_run),
    )

    if not args.dry_run:
        print("OK inserted forensics_events(kind=wallet_score)")
    print(json.dumps({"wallet": args.traced_wallet.strip(), "score": float(args.score), "severity": row["severity"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
