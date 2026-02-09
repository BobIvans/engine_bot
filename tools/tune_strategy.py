#!/usr/bin/env python3
"""tools/tune_strategy.py

PR-E.4 Parameter Tuning Harness - CLI entrypoint for running tuning sessions.

Usage:
    python tools/tune_strategy.py \
        --config integration/fixtures/config/daily_metrics.yaml \
        --ranges integration/fixtures/config/tuning_ranges.yaml \
        --trades integration/fixtures/trades.daily_metrics.jsonl \
        --snapshots integration/fixtures/token_snapshot.daily_metrics_all_skip.csv \
        --out tuning_results.json \
        --method grid \
        --seed 42

Flow:
1. Load base config and tuning ranges.
2. Load and normalize trades/snapshots (once).
3. Loop through generated configs:
   - Run preflight_and_simulate().
   - Collect sim_metrics.
4. Write tuning_results.v1.json.
"""

import argparse
import json
import sys
from typing import Any, Dict, Iterator, List, Optional

# Add parent dirs to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

import yaml

from integration.sim_preflight import preflight_and_simulate
from integration.token_snapshot_store import TokenSnapshotStore
from integration.trade_normalizer import normalize_trade
from strategy.tuning import generate_param_grid, extract_params_for_result


TUNING_SCHEMA_VERSION = "tuning_results.v1"


def load_yaml(path: str) -> Dict[str, Any]:
    """Load YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load JSONL file, return list of dicts."""
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_snapshots(path: str) -> TokenSnapshotStore:
    """Load token snapshots from CSV."""
    store = TokenSnapshotStore(csv_path=path)
    return store


def normalize_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize trades using the trade normalizer."""
    normalized = []
    for trade in trades:
        norm = normalize_trade(trade)
        if norm is not None:
            normalized.append(norm)
    return normalized


def run_tuning(
    *,
    config_path: str,
    ranges_path: str,
    trades_path: str,
    snapshots_path: str,
    out_path: str,
    method: str = "grid",
    samples: int = 10,
    seed: int = 42,
) -> None:
    """Run the tuning harness."""
    import os

    # Load configuration
    print(f"[tune_strategy] Loading base config: {config_path}", file=sys.stderr)
    base_config = load_yaml(config_path)

    print(f"[tune_strategy] Loading tuning ranges: {ranges_path}", file=sys.stderr)
    tuning_ranges = load_yaml(ranges_path)

    # Load trades once
    print(f"[tune_strategy] Loading trades: {trades_path}", file=sys.stderr)
    raw_trades = load_jsonl(trades_path)
    print(f"[tune_strategy] Loaded {len(raw_trades)} trades", file=sys.stderr)

    # Normalize trades
    print("[tune_strategy] Normalizing trades...", file=sys.stderr)
    trades_norm = normalize_trades(raw_trades)
    print(f"[tune_strategy] Normalized {len(trades_norm)} trades", file=sys.stderr)

    # Load snapshots
    print(f"[tune_strategy] Loading snapshots: {snapshots_path}", file=sys.stderr)
    snapshot_store = load_snapshots(snapshots_path)
    print(f"[tune_strategy] Loaded {snapshot_store.count()} snapshots", file=sys.stderr)

    # Generate configurations
    print(f"[tune_strategy] Generating configs with method={method}, samples={samples}...", file=sys.stderr)

    results: List[Dict[str, Any]] = []
    run_count = 0

    for config in generate_param_grid(
        base_config=base_config,
        ranges=tuning_ranges,
        method=method,
        samples=samples,
        seed=seed,
    ):
        run_count += 1

        # Run simulation
        sim_metrics = preflight_and_simulate(
            trades_norm=trades_norm,
            cfg=config,
            token_snapshot_store=snapshot_store,
            wallet_profile_store=None,  # Use config defaults
        )

        # Extract params for result
        params = extract_params_for_result(config, tuning_ranges)

        # Build result entry
        result_entry = {
            "params": params,
            "metrics": {
                "roi_total": sim_metrics.get("roi_total", 0.0),
                "winrate": sim_metrics.get("winrate", 0.0),
                "positions_closed": sim_metrics.get("positions_closed", 0),
                "avg_pnl_usd": sim_metrics.get("avg_pnl_usd", 0.0),
            },
        }
        results.append(result_entry)

        print(f"[tune_strategy] Run {run_count}: positions={sim_metrics.get('positions_closed', 0)}, roi={sim_metrics.get('roi_total', 0.0):.4f}", file=sys.stderr)

    # Build output
    output = {
        "schema_version": TUNING_SCHEMA_VERSION,
        "metadata": {
            "method": method,
            "samples": run_count,
            "seed": seed,
            "config_path": os.path.basename(config_path),
            "ranges_path": os.path.basename(ranges_path),
            "trades_path": os.path.basename(trades_path),
        },
        "results": results,
    }

    # Write output
    print(f"[tune_strategy] Writing results to: {out_path}", file=sys.stderr)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[tune_strategy] Completed {run_count} runs. Results saved.", file=sys.stderr)


def main() -> None:
    """Main entrypoint."""
    parser = argparse.ArgumentParser(
        description="Parameter Tuning Harness for Strategy Optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to base strategy config YAML",
    )
    parser.add_argument(
        "--ranges",
        required=True,
        help="Path to tuning ranges YAML",
    )
    parser.add_argument(
        "--trades",
        required=True,
        help="Path to trades JSONL file",
    )
    parser.add_argument(
        "--snapshots",
        required=True,
        help="Path to token snapshots CSV file",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to output JSON file",
    )
    parser.add_argument(
        "--method",
        default="grid",
        choices=["grid", "random"],
        help="Search method: grid (full cartesian) or random (sampling)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of samples for random search",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible results",
    )

    args = parser.parse_args()

    run_tuning(
        config_path=args.config,
        ranges_path=args.ranges,
        trades_path=args.trades,
        snapshots_path=args.snapshots,
        out_path=args.out,
        method=args.method,
        samples=args.samples,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
