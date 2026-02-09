#!/usr/bin/env python3
"""integration/ev_sweep.py

PR-9: Offline "threshold sweep" for +EV gate (min_edge_bps).

This module performs deterministic threshold sweeps writing results to results_v1.json.

Hard rules:
- No network, no randomness, no time.now - deterministic
- stdout must be empty for sweep tool
- Errors -> stderr with ERROR: prefix + exit 1
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, TextIO

# Schema version for results.v1
RESULTS_SCHEMA_VERSION = "results.v1"


def parse_thresholds(s: str) -> List[int]:
    """Parse comma-separated threshold values to list of integers.
    
    Args:
        s: Comma-separated string like "0,50,100"
    
    Returns:
        List of integer thresholds in bps
    
    Raises:
        ValueError: If parsing fails
    """
    if not s or not s.strip():
        raise ValueError("thresholds string is empty")
    
    thresholds = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = int(part)
        except ValueError:
            raise ValueError(f"invalid threshold value: '{part}' (expected integer)")
        if val < 0:
            raise ValueError(f"threshold must be non-negative: {val}")
        thresholds.append(val)
    
    if not thresholds:
        raise ValueError("no thresholds provided")
    
    return thresholds


def _load_csv(path: str, required_cols: List[str]) -> List[Dict[str, Any]]:
    """Load CSV file and return list of dicts."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load JSONL file and return list of dicts."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Best-effort attribute/dict getter."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    return default


def _ts_to_seconds(ts: Any) -> float:
    """Parse trade ts into seconds (deterministic)."""
    if ts is None:
        return 0.0
    
    try:
        return float(ts)
    except Exception:
        pass
    
    s = str(ts).strip()
    if not s:
        return 0.0
    
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    
    try:
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def compute_edge_bps(trade: Any, token_snap: Any, wallet_profile: Any, cfg: Dict[str, Any], mode_name: str) -> int:
    """Deterministic proxy for +EV gate (copied from sim_preflight.py)."""
    from integration.sim_preflight import _clamp
    
    win_p_raw = _get(wallet_profile, "winrate_30d", 0.0)
    try:
        win_p = float(win_p_raw) if win_p_raw is not None else 0.0
    except Exception:
        win_p = 0.0
    win_p = _clamp(win_p, 0.0, 1.0)
    
    modes = cfg.get("modes") if isinstance(cfg, dict) else None
    mode_cfg = (modes or {}).get(mode_name, {}) if isinstance(modes, dict) else {}
    
    try:
        tp = float(mode_cfg.get("tp_pct", 0.0))
    except Exception:
        tp = 0.0
    try:
        sl = abs(float(mode_cfg.get("sl_pct", 0.0)))
    except Exception:
        sl = 0.0
    
    gross_edge_pct = (win_p * tp) - ((1.0 - win_p) * sl)
    
    costs_bps = 0
    spread = _get(token_snap, "spread_bps", None)
    if spread is not None:
        try:
            costs_bps = int(float(spread))
        except Exception:
            costs_bps = 0
    
    edge_bps = int(round(gross_edge_pct * 10_000)) - costs_bps
    return int(edge_bps)


def _simulate_exit(
    entry_price: float,
    entry_ts_sec: float,
    future_ticks: List[Any],
    cfg_mode: Dict[str, Any],
) -> tuple[float, str]:
    """Simulate deterministic exit."""
    tp_pct = float(cfg_mode.get("tp_pct", 0.0))
    sl_pct = float(cfg_mode.get("sl_pct", 0.0))
    hold_sec_max = int(cfg_mode.get("hold_sec_max", 0))
    
    tp_level = entry_price * (1.0 + tp_pct)
    sl_level = entry_price * (1.0 + sl_pct)
    
    window_end = entry_ts_sec + float(hold_sec_max)
    
    last_price = entry_price
    saw_tick = False
    
    for tick in future_ticks:
        ts_sec = _ts_to_seconds(_get(tick, "ts", 0))
        if ts_sec <= entry_ts_sec:
            continue
        if ts_sec > window_end:
            break
        
        px_raw = _get(tick, "price", None)
        try:
            px = float(px_raw)
        except Exception:
            continue
        
        saw_tick = True
        last_price = px
        
        if px >= tp_level:
            return px, "TP"
        if px <= sl_level:
            return px, "SL"
    
    if not saw_tick:
        return entry_price, "TIME"
    return last_price, "TIME"


def run_ev_sweep(
    thresholds_bps: List[int],
    token_snapshot_csv: str,
    wallet_profiles_csv: str,
    trades_jsonl: str,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Run EV threshold sweep across multiple thresholds.
    
    Args:
        thresholds_bps: List of min_edge_bps thresholds to sweep
        token_snapshot_csv: Path to token snapshot CSV
        wallet_profiles_csv: Path to wallet profiles CSV
        trades_jsonl: Path to trades JSONL (entries + ticks)
        cfg: Configuration dict with modes and params
    
    Returns:
        Results dict with schema results.v1
    """
    # Load data
    token_snaps = _load_csv(token_snapshot_csv, ["mint", "spread_bps"])
    wallet_profs = _load_csv(wallet_profiles_csv, ["wallet", "winrate_30d"])
    trades = _load_jsonl(trades_jsonl)
    
    # Build lookup dicts
    snap_by_mint: Dict[str, Any] = {}
    for row in token_snaps:
        mint = _get(row, "mint", "")
        if mint:
            snap_by_mint[mint] = row
    
    wp_by_wallet: Dict[str, Any] = {}
    for row in wallet_profs:
        wallet = _get(row, "wallet", "")
        if wallet:
            wp_by_wallet[wallet] = row
    
    # Build tick index per mint
    from collections import defaultdict
    ticks_by_mint: Dict[str, List[Any]] = defaultdict(list)
    for t in trades:
        mint = _get(t, "mint", "") or ""
        if not mint:
            continue
        ts_sec = _ts_to_seconds(_get(t, "ts", 0))
        px_raw = _get(t, "price", None)
        try:
            px = float(px_raw) if px_raw is not None else 0.0
        except Exception:
            px = 0.0
        ticks_by_mint[mint].append((ts_sec, px, t))
    
    for mint, arr in ticks_by_mint.items():
        arr.sort(key=lambda x: x[0])
    
    # Identify entry candidates (BUY trades)
    entries: List[Dict[str, Any]] = []
    for t in trades:
        side = str(_get(t, "side", "")).upper()
        if side != "BUY":
            continue
        
        mint = _get(t, "mint", "") or ""
        wallet = _get(t, "wallet", "") or ""
        if not mint or not wallet:
            continue
        
        entry_price_raw = _get(t, "price", None)
        try:
            entry_price = float(entry_price_raw)
        except Exception:
            continue
        
        entry_ts_sec = _ts_to_seconds(_get(t, "ts", 0))
        
        extra = _get(t, "extra", None)
        mode = "U"
        if isinstance(extra, dict):
            m = extra.get("mode")
            if isinstance(m, str) and m.strip():
                mode = m
        
        entries.append({
            "trade": t,
            "mint": mint,
            "wallet": wallet,
            "entry_price": entry_price,
            "entry_ts_sec": entry_ts_sec,
            "mode": mode,
        })
    
    # Run sweep for each threshold
    sweep_rows = []
    for threshold in thresholds_bps:
        entered = 0
        skipped_missing_snap = 0
        skipped_missing_wallet = 0
        skipped_ev_below = 0
        pnl_total = 0.0
        notional_total = 0.0
        wins = 0
        exit_counts = {"TP": 0, "SL": 0, "TIME": 0}
        
        for entry in entries:
            mint = entry["mint"]
            wallet = entry["wallet"]
            
            snap = snap_by_mint.get(mint)
            if snap is None:
                skipped_missing_snap += 1
                continue
            
            wp = wp_by_wallet.get(wallet)
            if wp is None:
                skipped_missing_wallet += 1
                continue
            
            # Compute edge
            edge_bps = compute_edge_bps(
                trade=entry["trade"],
                token_snap=snap,
                wallet_profile=wp,
                cfg=cfg,
                mode_name=entry["mode"],
            )
            
            # Skip if threshold > 0 AND (edge is negative OR edge is below threshold)
            if threshold > 0 and (edge_bps < 0 or edge_bps < threshold):
                skipped_ev_below += 1
                continue
            
            # Simulate exit
            fut = ticks_by_mint.get(mint, [])
            mode_cfg = (cfg.get("modes") or {}).get(entry["mode"], {})
            exit_price, reason = _simulate_exit(
                entry_price=entry["entry_price"],
                entry_ts_sec=entry["entry_ts_sec"],
                future_ticks=[tick[2] for tick in fut],
                cfg_mode=mode_cfg,
            )
            
            # PnL
            notional_raw = _get(entry["trade"], "qty_usd", None)
            if notional_raw is None:
                notional_raw = _get(entry["trade"], "size_usd", None)
            try:
                notional = float(notional_raw) if notional_raw is not None else 1.0
            except Exception:
                notional = 1.0
            if notional <= 0:
                notional = 1.0
            
            pnl_usd = ((exit_price / entry["entry_price"]) - 1.0) * notional
            
            entered += 1
            pnl_total += pnl_usd
            notional_total += notional
            exit_counts[reason] = exit_counts.get(reason, 0) + 1
            if pnl_usd > 0:
                wins += 1
        
        winrate = (wins / entered) if entered else 0.0
        roi_total = (pnl_total / notional_total) if notional_total else 0.0
        avg_pnl = (pnl_total / entered) if entered else 0.0
        
        sim_metrics = {
            "positions_total": int(entered),
            "positions_closed": int(entered),
            "winrate": float(winrate),
            "roi_total": float(roi_total),
            "avg_pnl_usd": float(avg_pnl),
            "skipped_by_reason": {
                "missing_snapshot": int(skipped_missing_snap),
                "missing_wallet_profile": int(skipped_missing_wallet),
                "ev_below_threshold": int(skipped_ev_below),
            },
            "exit_reason_counts": exit_counts,
        }
        
        sweep_rows.append({
            "value": int(threshold),
            "sim_metrics": sim_metrics,
        })
    
    # Build fixture info from config
    fixture = {
        "strategy_name": cfg.get("strategy_name", "unknown"),
        "min_edge_swept": bool(cfg.get("min_edge_bps") is not None),
    }
    
    # Create run timestamp deterministically (fixed for reproducibility)
    run_ts = "1970-01-01T00:00:00Z"
    
    result: Dict[str, Any] = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "title": "PR-9 ev sweep",
        "run": {
            "created_utc": run_ts,
            "run_trace_id": "ev_sweep",
            "fixture": fixture,
        },
        "sweeps": [
            {
                "name": "min_edge_bps",
                "unit": "bps",
                "values": thresholds_bps,
                "rows": sweep_rows,
            }
        ],
        "notes": ["Deterministic offline sweep; no external APIs."],
    }
    
    return result


def write_results_atomic(path: str, obj: Dict[str, Any]) -> None:
    """Write results to file atomically (write to temp, then rename)."""
    import os
    import tempfile
    
    dir_path = os.path.dirname(path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".ev_sweep_",
        suffix=".tmp",
        dir=dir_path or ".",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.rename(tmp_path, path)
    except Exception:
        os.unlink(tmp_path) if os.path.exists(tmp_path) else None
        raise


def _main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PR-9: EV threshold sweep tool"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--allowlist",
        required=True,
        help="Path to wallet allowlist YAML",
    )
    parser.add_argument(
        "--token-snapshot",
        required=True,
        help="Path to token snapshot CSV",
    )
    parser.add_argument(
        "--wallet-profiles",
        required=True,
        help="Path to wallet profiles CSV",
    )
    parser.add_argument(
        "--trades-jsonl",
        required=True,
        help="Path to trades JSONL file",
    )
    parser.add_argument(
        "--thresholds-bps",
        required=True,
        help="Comma-separated threshold values in bps (e.g., 0,50,100)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for results JSON",
    )
    
    args = parser.parse_args()
    
    try:
        thresholds = parse_thresholds(args.thresholds_bps)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Load config
    try:
        import yaml
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"ERROR: failed to load config: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Run sweep
    try:
        result = run_ev_sweep(
            thresholds_bps=thresholds,
            token_snapshot_csv=args.token_snapshot,
            wallet_profiles_csv=args.wallet_profiles,
            trades_jsonl=args.trades_jsonl,
            cfg=cfg,
        )
    except Exception as e:
        print(f"ERROR: sweep failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Write results
    try:
        write_results_atomic(args.out, result)
    except Exception as e:
        print(f"ERROR: failed to write results: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Success - no stdout output per requirements
    print("[ev_sweep] OK ✅", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    _main()
