#!/usr/bin/env python3
"""integration/write_signal.py

Small helper to insert a wallet-copy signal into CANON ClickHouse tables.

This is intentionally thin and strategy-owned (integration/**):
- Writes into vendor/gmee_canon schema table: signals_raw
- Does NOT change CANON or re-implement exit math

Typical use (after ./scripts/smoke.sh brought up CH):
  python integration/write_signal.py \
    --traced-wallet <SOL_WALLET> \
    --token-mint <MINT> --pool-id <POOL>

If you use an allowlist:
  python integration/write_signal.py \
    --allowlist strategy/wallet_allowlist.yaml --require-allowlist ...

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
    # ClickHouse DateTime64(3) friendly format
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _load_payload(payload_json: Optional[str], payload_file: Optional[str]) -> Dict[str, Any]:
    if payload_json and payload_file:
        raise SystemExit("Provide only one of --payload-json or --payload-file")
    if payload_file:
        p = Path(payload_file)
        return json.loads(p.read_text(encoding="utf-8"))
    if payload_json:
        return json.loads(payload_json)
    return {}


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


def insert_signal(
    *,
    cfg: ClickHouseConfig,
    chain: str,
    env: str,
    source: str,
    traced_wallet: str,
    token_mint: str,
    pool_id: str,
    ts: str,
    trace_id: str,
    signal_id: str,
    payload: Dict[str, Any],
    allowlist_path: str = "",
    require_allowlist: bool = False,
    log_allowlist_version: bool = True,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    traced_wallet = traced_wallet.strip()

    allowlist_hash: Optional[str] = None
    allowlist_count: int = 0
    allowlist_row: Optional[Dict[str, Any]] = None

    if allowlist_path:
        wallets, allowlist_hash = load_allowlist(allowlist_path)
        allowlist_count = len(wallets)
        if require_allowlist and traced_wallet not in set(wallets):
            raise SystemExit(f"Wallet not in allowlist: {traced_wallet}")
        payload.setdefault("allowlist_hash", allowlist_hash)

        if log_allowlist_version:
            allowlist_row = _mk_allowlist_version_row(
                ts=ts,
                chain=chain,
                env=env,
                path=allowlist_path,
                wallets_count=allowlist_count,
                allowlist_hash=allowlist_hash,
            )

    # default identifiers
    trace_id = trace_id or str(uuid.uuid4())

    # Stable-ish signal_id: if not provided, make it deterministic per (wallet, mint, pool, ts)
    if not signal_id:
        signal_id = f"sig_{uuid.uuid5(uuid.NAMESPACE_URL, traced_wallet + '|' + token_mint + '|' + pool_id + '|' + ts)}"

    row = {
        "trace_id": trace_id,
        "ts": ts,
        "chain": chain,
        "env": env,
        "source": source,
        "signal_id": signal_id,
        "traced_wallet": traced_wallet,
        "token_mint": token_mint,
        "pool_id": pool_id,
        "payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        # ingested_at is DEFAULT now64(3)
    }

    if dry_run:
        print("[dry-run] would insert into signals_raw:", file=sys.stderr)
        print(json.dumps(row, ensure_ascii=False, indent=2), file=sys.stderr)
        if allowlist_row:
            print("[dry-run] would also insert forensics_events(kind=allowlist_version):", file=sys.stderr)
            print(json.dumps(allowlist_row, ensure_ascii=False, indent=2), file=sys.stderr)
        return row, allowlist_row

    runner = make_runner(cfg)
    if allowlist_row:
        runner.insert_json_each_row("forensics_events", [allowlist_row])
    runner.insert_json_each_row("signals_raw", [row])

    return row, allowlist_row


def main() -> None:
    ap = argparse.ArgumentParser(description="Insert a signal row into signals_raw.")
    ap.add_argument("--ch-url", default=None, help="Override CLICKHOUSE_URL")
    ap.add_argument("--ch-user", default=None, help="Override CLICKHOUSE_USER")
    ap.add_argument("--ch-password", default=None, help="Override CLICKHOUSE_PASSWORD")

    ap.add_argument("--chain", default="solana")
    ap.add_argument("--env", default="canary")
    ap.add_argument("--source", default="wallet_copy")
    ap.add_argument("--signal-id", default="")
    ap.add_argument("--trace-id", default="")
    ap.add_argument("--ts", default="", help="Optional ts override (DateTime64(3) string)")

    ap.add_argument("--traced-wallet", required=True)
    ap.add_argument("--token-mint", default="")
    ap.add_argument("--pool-id", default="")

    ap.add_argument("--allowlist", "--allowlist-path", dest="allowlist", default="", help="Optional allowlist path")
    ap.add_argument("--require-allowlist", action="store_true", help="Fail if traced wallet not in allowlist")
    ap.add_argument("--no-log-allowlist-version", action="store_true", help="Do not write allowlist_version forensics event")

    ap.add_argument("--payload-json", default=None)
    ap.add_argument("--payload-file", default=None)

    ap.add_argument("--dry-run", action="store_true", help="Validate inputs and print rows, without ClickHouse writes")
    args = ap.parse_args()

    cfg = ClickHouseConfig.from_args(args.ch_url, args.ch_user, args.ch_password)
    ts = args.ts or _utc_now_iso_ms()
    payload = _load_payload(args.payload_json, args.payload_file)

    row, _ = insert_signal(
        cfg=cfg,
        chain=args.chain,
        env=args.env,
        source=args.source,
        traced_wallet=args.traced_wallet,
        token_mint=args.token_mint,
        pool_id=args.pool_id,
        ts=ts,
        trace_id=args.trace_id,
        signal_id=args.signal_id,
        payload=payload,
        allowlist_path=args.allowlist,
        require_allowlist=bool(args.require_allowlist),
        log_allowlist_version=not bool(args.no_log_allowlist_version),
        dry_run=bool(args.dry_run),
    )

    if not args.dry_run:
        print("OK inserted signals_raw")
    print(json.dumps({"trace_id": row["trace_id"], "signal_id": row["signal_id"], "ts": row["ts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
