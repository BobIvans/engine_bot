#!/usr/bin/env python3
"""integration/walk_forward.py

PR-D.1: Walk-Forward Backtest Harness.

This module slices trades into temporal windows and runs simulations for each window.

Hard rules:
- No network, no randomness, no time.now - deterministic
- stdout must be empty for success
- Errors -> stderr with ERROR: prefix + exit 1
- Determinism: sort by ts, no datetime.now()
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# Schema version for results.v1
RESULTS_SCHEMA_VERSION = "results.v1"


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


def _seconds_to_iso(ts_sec: float) -> str:
    """Convert seconds since epoch to ISO date string (YYYY-MM-DD)."""
    dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


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


def _normalize_trades(trades: List[Dict[str, Any]]) -> List[Any]:
    """Normalize trades dicts to objects with ts field.

    Creates simple objects with ts attribute for consistent access.
    """
    normalized = []
    for t in trades:
        ts = _get(t, "ts", 0)
        ts_sec = _ts_to_seconds(ts)
        # Create a simple object-like dict with ts_sec for sorting
        t["_ts_sec"] = ts_sec
        normalized.append(t)
    return normalized


def generate_windows(
    min_ts_sec: float,
    max_ts_sec: float,
    window_days: int,
    step_days: int,
) -> List[Tuple[float, float]]:
    """Generate walk-forward windows.

    Args:
        min_ts_sec: Global minimum timestamp in seconds
        max_ts_sec: Global maximum timestamp in seconds
        window_days: Window size in days
        step_days: Step size in days

    Returns:
        List of (window_start_sec, window_end_sec) tuples
    """
    window_sec = window_days * 86400
    step_sec = step_days * 86400

    windows = []
    current_start = min_ts_sec

    while current_start <= max_ts_sec:
        window_end = current_start + window_sec
        windows.append((current_start, window_end))
        current_start += step_sec

    return windows


def run_walk_forward(
    trades_jsonl: str,
    config_path: str,
    window_days: int,
    step_days: int,
    token_snapshot_csv: str,
    wallet_profiles_csv: str,
) -> Dict[str, Any]:
    """Run walk-forward backtest across temporal windows.

    Args:
        trades_jsonl: Path to trades JSONL file
        config_path: Path to config YAML file
        window_days: Window size in days
        step_days: Step size in days
        token_snapshot_csv: Path to token snapshot CSV
        wallet_profiles_csv: Path to wallet profiles CSV

    Returns:
        Results dict with schema results.v1
    """
    # Load config
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Load stores
    from integration.token_snapshot_store import TokenSnapshotStore
    from integration.wallet_profile_store import WalletProfileStore

    token_snapshot_store = TokenSnapshotStore.from_csv(token_snapshot_csv)
    wallet_profile_store = WalletProfileStore.from_csv(wallet_profiles_csv)

    # Load and normalize trades
    trades = _load_jsonl(trades_jsonl)
    trades_norm = _normalize_trades(trades)

    # Sort by timestamp for determinism
    trades_norm.sort(key=lambda t: _get(t, "_ts_sec", 0))

    if not trades_norm:
        raise ValueError("No trades found in input file")

    # Get global min/max ts
    min_ts_sec = min(_get(t, "_ts_sec", 0) for t in trades_norm)
    max_ts_sec = max(_get(t, "_ts_sec", 0) for t in trades_norm)

    # Generate windows
    windows = generate_windows(min_ts_sec, max_ts_sec, window_days, step_days)

    # Import preflight_and_simulate
    from integration.sim_preflight import preflight_and_simulate

    # Run simulation for each window
    sweep_rows = []
    for window_start_sec, window_end_sec in windows:
        # Filter trades to this window: start <= t.ts < end
        window_trades = [
            t for t in trades_norm
            if _get(t, "_ts_sec", 0) >= window_start_sec and _get(t, "_ts_sec", 0) < window_end_sec
        ]

        # Skip empty windows
        if not window_trades:
            continue

        # Run preflight and simulate
        sim_metrics = preflight_and_simulate(
            trades_norm=window_trades,
            cfg=cfg,
            token_snapshot_store=token_snapshot_store,
            wallet_profile_store=wallet_profile_store,
        )

        # Extract window_start_date ISO string
        window_start_date = _seconds_to_iso(window_start_sec)

        sweep_rows.append({
            "window_start": window_start_date,
            **sim_metrics,
        })

    # Create run timestamp deterministically (fixed for reproducibility)
    run_ts = "1970-01-01T00:00:00Z"

    result: Dict[str, Any] = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "title": "PR-D walk forward",
        "run": {
            "created_utc": run_ts,
            "run_trace_id": "walk_forward",
        },
        "sweeps": [
            {
                "name": "walk_forward",
                "unit": "date_iso",
                "values": [row["window_start"] for row in sweep_rows],
                "rows": sweep_rows,
            }
        ],
        "notes": ["Deterministic walk-forward backtest; no external APIs."],
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
        prefix=".walk_forward_",
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
        description="PR-D.1: Walk-Forward Backtest Harness"
    )
    parser.add_argument(
        "--trades",
        required=True,
        help="Path to trades JSONL file",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        required=True,
        help="Window size in days (int)",
    )
    parser.add_argument(
        "--step-days",
        type=int,
        required=True,
        help="Step size in days (int)",
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
        "--out",
        required=True,
        help="Output path for results JSON",
    )

    args = parser.parse_args()

    # Validate window/step parameters
    if args.window_days <= 0:
        print(f"ERROR: window-days must be positive", file=sys.stderr)
        sys.exit(1)
    if args.step_days <= 0:
        print(f"ERROR: step-days must be positive", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_walk_forward(
            trades_jsonl=args.trades,
            config_path=args.config,
            window_days=args.window_days,
            step_days=args.step_days,
            token_snapshot_csv=args.token_snapshot,
            wallet_profiles_csv=args.wallet_profiles,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Write results
    try:
        write_results_atomic(args.out, result)
    except Exception as e:
        print(f"ERROR: failed to write results: {e}", file=sys.stderr)
        sys.exit(1)

    # Silent success - only stderr output
    print("[walk_forward] OK ✅", file=sys.stderr)


if __name__ == "__main__":
    _main()
