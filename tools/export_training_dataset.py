#!/usr/bin/env python3
"""Export a deterministic training dataset for miniML.

Input: JSONL trades (trade_v1 or raw records accepted by the normalizer).
Optional: token snapshots, wallet profiles.
Output: Parquet (via duckdb, no pandas required).

Exit codes:
  0 OK
  2 Bad input (file missing / invalid jsonl)
  3 Internal error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Ensure repo root is importable when invoked as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from features.trade_features import FEATURE_KEYS_V2, build_features_v2

from integration.token_snapshot_store import TokenSnapshotStore
from integration.trade_normalizer import normalize_trade_record
from integration.trade_types import Trade
from integration.wallet_profile_store import WalletProfileStore

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_INTERNAL = 3


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _load_snapshot_store(path: str) -> TokenSnapshotStore:
    if path.lower().endswith(".parquet"):
        return TokenSnapshotStore.from_parquet(path)
    return TokenSnapshotStore.from_csv(path)


def _load_wallet_store(path: str) -> WalletProfileStore:
    if path.lower().endswith(".parquet"):
        return WalletProfileStore.from_parquet(path)
    return WalletProfileStore.from_csv(path)


def _iter_jsonl(path: str) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                raise ValueError(f"invalid_json at line {lineno}")
            if not isinstance(obj, dict):
                raise ValueError(f"invalid_json_not_object at line {lineno}")
            yield lineno, obj


def _normalize(obj: Dict[str, Any], lineno: int) -> Trade:
    out = normalize_trade_record(obj, lineno=lineno)
    if isinstance(out, dict) and out.get("_reject"):
        # For dataset export we treat rejects as bad input: users should pass
        # normalized trade_v1 jsonl for training.
        reason = out.get("reason")
        detail = out.get("detail")
        raise ValueError(f"trade_reject at line {lineno}: {reason} {detail}")
    if not isinstance(out, Trade):
        raise ValueError(f"unexpected_normalize_output at line {lineno}")
    return out


def _meta_row(t: Trade) -> Dict[str, Any]:
    # Keep meta stable and simple. Use empty string for missing optional fields.
    return {
        "ts": t.ts,
        "wallet": t.wallet,
        "mint": t.mint,
        "side": t.side,
        "price": float(t.price) if t.price is not None else 0.0,
        "size_usd": float(t.size_usd) if t.size_usd is not None else 0.0,
        "tx_hash": getattr(t, "tx_hash", "") or "",
        "platform": getattr(t, "platform", "") or "",
    }


def _write_parquet_or_csv(rows: List[Dict[str, Any]], out_parquet: str) -> str:
    """Write Parquet via duckdb if available, otherwise write CSV.

    Returns the path written.
    """
    try:
        import duckdb  # type: ignore
    except Exception:
        duckdb = None

    os.makedirs(os.path.dirname(out_parquet) or ".", exist_ok=True)

    if duckdb is None:
        # CSV fallback (keeps repo usable even in minimal envs)
        import csv

        out_csv = out_parquet
        if out_csv.lower().endswith(".parquet"):
            out_csv = out_csv[:-7] + "csv"

        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            fieldnames = list(rows[0].keys()) if rows else []
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        _eprint(
            f"WARN: duckdb is not available; wrote CSV instead of Parquet: {out_csv}"
        )
        return out_csv

    con = duckdb.connect(database=":memory:")

    # Create table with an explicit schema (stable, deterministic)
    con.execute(
        """
        CREATE TABLE dataset (
          ts VARCHAR,
          wallet VARCHAR,
          mint VARCHAR,
          side VARCHAR,
          price DOUBLE,
          size_usd DOUBLE,
          tx_hash VARCHAR,
          platform VARCHAR,
          f_trade_size_usd DOUBLE,
          f_price DOUBLE,
          f_side_is_buy INTEGER,
          f_token_liquidity_usd DOUBLE,
          f_token_spread_bps DOUBLE,
          f_wallet_roi_30d_pct DOUBLE,
          f_wallet_winrate_30d DOUBLE,
          f_wallet_trades_30d DOUBLE,
          f_token_vol_30s DOUBLE,
          f_token_impulse_5m DOUBLE,
          f_smart_money_share DOUBLE,
            y_has_future_ticks INTEGER,
            y_horizon_sec INTEGER,
            y_roi_horizon_pct DOUBLE,
            y_max_upside_horizon_pct DOUBLE,
            y_max_drawdown_horizon_pct DOUBLE
        )
        """
    )

    insert_sql = (
        "INSERT INTO dataset VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    values = []
    for r in rows:
        values.append(
            (
                r.get("ts", ""),
                r.get("wallet", ""),
                r.get("mint", ""),
                r.get("side", ""),
                float(r.get("price", 0.0) or 0.0),
                float(r.get("size_usd", 0.0) or 0.0),
                r.get("tx_hash", ""),
                r.get("platform", ""),
                float(r.get("f_trade_size_usd", 0.0) or 0.0),
                float(r.get("f_price", 0.0) or 0.0),
                int(r.get("f_side_is_buy", 0) or 0),
                float(r.get("f_token_liquidity_usd", 0.0) or 0.0),
                float(r.get("f_token_spread_bps", 0.0) or 0.0),
                float(r.get("f_wallet_roi_30d_pct", 0.0) or 0.0),
                float(r.get("f_wallet_winrate_30d", 0.0) or 0.0),
                float(r.get("f_wallet_trades_30d", 0.0) or 0.0),
                float(r.get("f_token_vol_30s", 0.0) or 0.0),
                float(r.get("f_token_impulse_5m", 0.0) or 0.0),
                float(r.get("f_smart_money_share", 0.0) or 0.0),
                int(r.get("y_has_future_ticks", 0) or 0),
                int(r.get("y_horizon_sec", 0) or 0),
                r.get("y_roi_horizon_pct", None),
                r.get("y_max_upside_horizon_pct", None),
                r.get("y_max_drawdown_horizon_pct", None),
            )
        )
    con.executemany(insert_sql, values)
    con.execute("COPY dataset TO ? (FORMAT PARQUET)", [out_parquet])
    con.close()
    return out_parquet



def _parse_ts_any(ts_val: Any) -> Optional[datetime]:
    """Parse ts that may be datetime, ISO string, or unix seconds."""
    if ts_val is None:
        return None
    if isinstance(ts_val, datetime):
        # Normalize to UTC-aware
        return ts_val.astimezone(timezone.utc) if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    # Numeric unix epoch seconds
    if isinstance(ts_val, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts_val), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(ts_val, str):
        s = ts_val.strip()
        if not s:
            return None
        # Support trailing Z
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _coerce_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        if x != x:  # NaN
            return None
        return x
    except Exception:
        return None


def add_labels_v1_to_rows(rows: List[Dict[str, Any]], horizon_sec: int) -> List[Dict[str, Any]]:
    """Add deterministic labels y_* to dataset rows.

    Labels are computed FREE-FIRST using only future rows of the same mint within the
    interval (entry_ts, entry_ts + horizon_sec].

    Required per-row fields: ts, mint, price.

    Columns added (always present):
      - y_has_future_ticks (0/1)
      - y_horizon_sec
      - y_roi_horizon_pct
      - y_max_upside_horizon_pct
      - y_max_drawdown_horizon_pct
    """
    # Pre-fill columns so they always exist.
    for r in rows:
        r['y_has_future_ticks'] = 0
        # Horizon is a dataset parameter (sampling window), not a label.
        # Keep it stable across all rows, regardless of whether future ticks exist.
        r['y_horizon_sec'] = int(horizon_sec)
        r['y_roi_horizon_pct'] = None
        r['y_max_upside_horizon_pct'] = None
        r['y_max_drawdown_horizon_pct'] = None

    # Group indices by mint
    by_mint: Dict[str, List[int]] = {}
    for i, r in enumerate(rows):
        mint = r.get('mint')
        if not isinstance(mint, str) or not mint:
            continue
        by_mint.setdefault(mint, []).append(i)

    from bisect import bisect_right

    for mint, idxs in by_mint.items():
        # Build sortable tuples (ts_dt, original_index)
        items = []
        for i in idxs:
            dt = _parse_ts_any(rows[i].get('ts'))
            if dt is None:
                continue
            items.append((dt, i))
        if not items:
            continue
        # Deterministic stable ordering: ts then original index
        items.sort(key=lambda x: (x[0], x[1]))
        times = [t for (t, _) in items]
        ord_idxs = [i for (_, i) in items]

        for pos, row_i in enumerate(ord_idxs):
            entry_dt = times[pos]
            entry_price = _coerce_float(rows[row_i].get('price'))
            # Guard: invalid/zero price => keep y_* pct as null.
            if entry_price is None or entry_price <= 0:
                continue
            end_dt = entry_dt + timedelta(seconds=int(horizon_sec))
            end_pos = bisect_right(times, end_dt)
            if end_pos <= pos + 1:
                continue
            future_ord = ord_idxs[pos + 1 : end_pos]
            fut_prices = [
                _coerce_float(rows[j].get('price'))
                for j in future_ord
            ]
            fut_prices = [p for p in fut_prices if p is not None]
            if not fut_prices:
                continue
            last_price = fut_prices[-1]
            max_price = max(fut_prices)
            min_price = min(fut_prices)
            rows[row_i]['y_has_future_ticks'] = 1
            rows[row_i]['y_roi_horizon_pct'] = 100.0 * (last_price / entry_price - 1.0)
            rows[row_i]['y_max_upside_horizon_pct'] = 100.0 * (max_price / entry_price - 1.0)
            rows[row_i]['y_max_drawdown_horizon_pct'] = 100.0 * (min_price / entry_price - 1.0)

    return rows

def _build_coverage_v1(rows: List[Dict[str, Any]], label_horizon_sec: int, snap_present_rows: int, wallet_present_rows: int) -> Dict[str, Any]:
    rows_total = len(rows)
    # Expected label columns (always present after add_labels_v1_to_rows)
    label_cols = [
        "y_has_future_ticks",
        "y_horizon_sec",
        "y_roi_horizon_pct",
        "y_max_upside_horizon_pct",
        "y_max_drawdown_horizon_pct",
    ]

    missing = [c for c in label_cols if rows_total > 0 and c not in rows[0]]
    if missing:
        raise KeyError(",".join(missing))

    def is_null(v: Any) -> bool:
        if v is None:
            return True
        try:
            import math

            return isinstance(v, float) and math.isnan(v)
        except Exception:
            return False

    labels: Dict[str, Dict[str, int]] = {}
    for c in label_cols:
        nn = 0
        for r in rows:
            if not is_null(r.get(c)):
                nn += 1
        labels[c] = {"non_null": nn, "null": rows_total - nn}

    # Presence: future ticks by label
    has_future_ticks_rows = 0
    for r in rows:
        try:
            if int(r.get("y_has_future_ticks") or 0) == 1:
                has_future_ticks_rows += 1
        except Exception:
            continue

    # Non-null rates for key columns (labels + features contract keys)
    key_cols = [
        "y_roi_horizon_pct",
        "y_max_upside_horizon_pct",
        "y_max_drawdown_horizon_pct",
        "y_has_future_ticks",
        "y_horizon_sec",
    ] + list(FEATURE_KEYS_V2)

    non_null_rate: Dict[str, float] = {}
    if rows_total > 0:
        for c in key_cols:
            if c not in rows[0]:
                continue
            nn = 0
            for r in rows:
                if not is_null(r.get(c)):
                    nn += 1
            non_null_rate[c] = nn / float(rows_total)

    return {
        "schema_version": "coverage.v1",
        "exporter": "export_training_dataset",
        "label_horizon_sec": int(label_horizon_sec),
        "rows_total": int(rows_total),
        "rows_written": int(rows_total),
        "presence": {
            "has_token_snapshot_rows": int(snap_present_rows),
            "has_wallet_profile_rows": int(wallet_present_rows),
            "has_future_ticks_rows": int(has_future_ticks_rows),
        },
        "labels": labels,
        "non_null_rate": non_null_rate,
    }


def _emit_coverage(coverage: Dict[str, Any], coverage_out: Optional[str], coverage_stderr: bool) -> None:
    # File output (pretty) is stable and deterministic.
    if coverage_out:
        try:
            out_path = Path(coverage_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(coverage, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(out_path)
        except Exception as e:
            raise IOError(f"{coverage_out}: {type(e).__name__}: {e}")

    if coverage_stderr:
        # Minified JSON, exactly one line.
        line = json.dumps(
            coverage,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        _eprint(f"COVERAGE: {line}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades-jsonl", required=True)
    ap.add_argument("--token-snapshot", default=None)
    ap.add_argument("--wallet-profiles", default=None)
    ap.add_argument("--out-parquet", required=True)

    ap.add_argument(
        "--label-horizon-sec",
        type=int,
        default=300,
        help="Label horizon in seconds for y_* calculations (default: 300).",
    )

    ap.add_argument(
        "--coverage-out",
        default=None,
        help="Optional path to write coverage summary JSON (coverage.v1).",
    )
    ap.add_argument(
        "--coverage-stderr",
        action="store_true",
        help="If set, emit one stderr line 'COVERAGE: <json>' with coverage summary.",
    )

    args = ap.parse_args()

    try:
        snap_store: Optional[TokenSnapshotStore] = (
            _load_snapshot_store(args.token_snapshot) if args.token_snapshot else None
        )
        wallet_store: Optional[WalletProfileStore] = (
            _load_wallet_store(args.wallet_profiles) if args.wallet_profiles else None
        )

        snap_present_rows = 0
        wallet_present_rows = 0

        rows: List[Dict[str, Any]] = []
        for lineno, obj in _iter_jsonl(args.trades_jsonl):
            t = _normalize(obj, lineno)
            snap = snap_store.get_latest(t.mint) if snap_store else None
            wp = wallet_store.get(t.wallet) if wallet_store else None
            if snap is not None:
                snap_present_rows += 1
            if wp is not None:
                wallet_present_rows += 1
            feats = build_features_v2(t, wp, snap)
            # Enforce contract keys (defensive)
            for k in FEATURE_KEYS_V2:
                if k not in feats:
                    feats[k] = 0.0
            row = _meta_row(t)
            row.update(feats)
            rows.append(row)

        # Labels v1 (deterministic, free-first): computed only from in-dataset future trades.
        rows = add_labels_v1_to_rows(rows, horizon_sec=int(args.label_horizon_sec))

        # Optional coverage summary (never written to stdout).
        if args.coverage_out or args.coverage_stderr:
            try:
                coverage = _build_coverage_v1(
                    rows,
                    label_horizon_sec=int(args.label_horizon_sec),
                    snap_present_rows=snap_present_rows,
                    wallet_present_rows=wallet_present_rows,
                )
                _emit_coverage(
                    coverage,
                    coverage_out=args.coverage_out,
                    coverage_stderr=bool(args.coverage_stderr),
                )
            except Exception as e:
                _eprint(
                    f"ERROR: Failed to write coverage JSON: {args.coverage_out or '<stderr>'}: {type(e).__name__}: {e}"
                )
                return EXIT_INTERNAL

        out_path = _write_parquet_or_csv(rows, args.out_parquet)
        print(
            json.dumps(
                {
                    "ok": True,
                    "rows": len(rows),
                    "out": out_path,
                    "feature_keys": list(FEATURE_KEYS_V1),
                },
                ensure_ascii=False,
            )
        )
        return EXIT_OK
    except FileNotFoundError as e:
        _eprint(f"BAD_INPUT: file not found: {e}")
        return EXIT_BAD_INPUT
    except ValueError as e:
        _eprint(f"BAD_INPUT: {e}")
        return EXIT_BAD_INPUT
    except Exception as e:
        _eprint(f"INTERNAL: {type(e).__name__}: {e}")
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
