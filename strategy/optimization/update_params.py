#!/usr/bin/env python3
"""strategy/optimization/update_params.py

PR-Q.1 Stats Feedback Loop (Auto-update Params)

Offline script that analyzes daily_metrics and updates dynamic parameters
in params_base.yaml using EWMA smoothing.

Usage:
    python strategy/optimization/update_params.py \
        --metrics integration/fixtures/trades.daily_metrics.jsonl \
        --config strategy/config/params_base.yaml \
        --output /tmp/params_base_updated.yaml

    # With summary JSON (stdout):
    python strategy/optimization/update_params.py ... --summary-json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)


@dataclass
class UpdateConfig:
    """Configuration for parameter updates."""
    enabled: bool = True
    min_days_required: int = 7
    ewma_alpha: float = 0.15
    bounds: Dict[str, List[float]] = None
    max_change_per_run: float = 0.20

    def __post_init__(self):
        if self.bounds is None:
            self.bounds = {
                "mu_win": [0.01, 0.25],
                "mu_loss": [0.005, 0.15],
                "p0": [0.52, 0.65],
                "delta0": [0.00, 0.04],
            }


@dataclass
class ModeStats:
    """Statistics for a single mode."""
    mode: str
    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0
    total_win_pct: float = 0.0
    total_loss_pct: float = 0.0

    @property
    def winrate(self) -> float:
        if self.n_trades == 0:
            return 0.0
        return self.n_wins / self.n_trades

    @property
    def avg_win_pct(self) -> float:
        if self.n_wins == 0:
            return 0.0
        return self.total_win_pct / self.n_wins

    @property
    def avg_loss_pct(self) -> float:
        if self.n_losses == 0:
            return 0.0
        return self.total_loss_pct / self.n_losses


def load_metrics(metrics_path: str, lookback_days: int = 30) -> List[Dict]:
    """Load daily metrics from JSONL file.

    Args:
        metrics_path: Path to metrics JSONL file.
        lookback_days: Only load trades from last N days.

    Returns:
        List of trade metrics dicts.
    """
    metrics_path = Path(metrics_path)
    if not metrics_path.exists():
        logger.warning(f"Metrics file not found: {metrics_path}")
        return []

    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    trades = []

    with open(metrics_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trade = json.loads(line)
                # Parse timestamp
                ts = trade.get("ts")
                if ts:
                    try:
                        trade_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if trade_dt < cutoff_date:
                            continue
                    except (ValueError, TypeError):
                        pass
                trades.append(trade)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON line: {line[:50]}...")

    logger.info(f"Loaded {len(trades)} trades from last {lookback_days} days")
    return trades


def compute_mode_stats(trades: List[Dict]) -> Dict[str, ModeStats]:
    """Compute statistics grouped by mode.

    Supports two formats:
    1. Individual trades: {"mode": "U", "price": 1.00, "exit_price": 1.05}
    2. Aggregated: {"pnl_aggregation": {"U": {"avg_win_pct": 0.045, "avg_loss_pct": 0.022, "trade_count": 25, "win_rate": 0.68}}}

    Args:
        trades: List of trade metrics.

    Returns:
        Dict mapping mode -> ModeStats.
    """
    # Check if trades are in aggregated format
    if trades and "pnl_aggregation" in trades[0]:
        # Aggregated format
        aggregated: Dict[str, Dict] = {}
        for trade in trades:
            pnl_agg = trade.get("pnl_aggregation", {})
            for mode, stats in pnl_agg.items():
                if mode not in aggregated:
                    aggregated[mode] = {
                        "total_win_pct": 0.0,
                        "total_loss_pct": 0.0,
                        "n_trades": 0,
                        "n_wins": 0,
                    }
                agg = aggregated[mode]
                agg["total_win_pct"] += stats.get("avg_win_pct", 0.0) * stats.get("trade_count", 0)
                agg["total_loss_pct"] += stats.get("avg_loss_pct", 0.0) * stats.get("trade_count", 0)
                agg["n_trades"] += stats.get("trade_count", 0)
                agg["n_wins"] += int(stats.get("win_rate", 0.0) * stats.get("trade_count", 0))

        stats: Dict[str, ModeStats] = {}
        for mode, agg in aggregated.items():
            mode_stats = ModeStats(mode=mode)
            mode_stats.n_trades = agg["n_trades"]
            mode_stats.n_wins = agg["n_wins"]
            mode_stats.n_losses = max(0, agg["n_trades"] - agg["n_wins"])
            mode_stats.total_win_pct = agg["total_win_pct"]
            mode_stats.total_loss_pct = agg["total_loss_pct"]
            stats[mode] = mode_stats

        # Log stats
        for mode, mode_stats in stats.items():
            logger.info(
                f"Mode {mode}: {mode_stats.n_trades} trades, "
                f"winrate={mode_stats.winrate:.2%}, "
                f"avg_win={mode_stats.avg_win_pct:.4f}, "
                f"avg_loss={mode_stats.avg_loss_pct:.4f}"
            )

        return stats

    # Individual trades format (original logic)
    # Group trades by mode
    mode_trades: Dict[str, List[Dict]] = {}
    for trade in trades:
        mode = trade.get("mode")
        if not mode:
            # Try to infer mode from configuration or skip
            mode = "U"  # Default
        if mode not in mode_trades:
            mode_trades[mode] = []
        mode_trades[mode].append(trade)

    # Compute stats per mode
    stats: Dict[str, ModeStats] = {}
    for mode, mode_trade_list in mode_trades.items():
        mode_stats = ModeStats(mode=mode)

        for trade in mode_trade_list:
            side = trade.get("side", "").upper()
            # Calculate ROI from price change
            entry_price = trade.get("price")
            exit_price = trade.get("exit_price") or trade.get("final_price")

            if entry_price and exit_price:
                roi_pct = (exit_price - entry_price) / entry_price
            else:
                roi_pct = 0.0

            mode_stats.n_trades += 1

            if roi_pct > 0:
                mode_stats.n_wins += 1
                mode_stats.total_win_pct += roi_pct
            else:
                mode_stats.n_losses += 1
                mode_stats.total_loss_pct += abs(roi_pct)

        stats[mode] = mode_stats

    # Log stats
    for mode, mode_stats in stats.items():
        logger.info(
            f"Mode {mode}: {mode_stats.n_trades} trades, "
            f"winrate={mode_stats.winrate:.2%}, "
            f"avg_win={mode_stats.avg_win_pct:.4f}, "
            f"avg_loss={mode_stats.avg_loss_pct:.4f}"
        )

    return stats


def apply_ewma(
    current_value: float,
    new_value: float,
    alpha: float,
) -> float:
    """Apply EWMA smoothing.

    Args:
        current_value: Current EWMA value.
        new_value: New observation.
        alpha: Smoothing factor (0 < alpha <= 1).

    Returns:
        Updated EWMA value.
    """
    if current_value == 0:
        return new_value
    return alpha * new_value + (1 - alpha) * current_value


def clamp_value(value: float, bounds: List[float]) -> float:
    """Clamp value to bounds.

    Args:
        value: Value to clamp.
        bounds: [min, max] bounds.

    Returns:
        Clamped value.
    """
    return max(bounds[0], min(bounds[1], value))


def compute_updated_params(
    current_params: Dict[str, Any],
    stats: Dict[str, ModeStats],
    config: UpdateConfig,
) -> Dict[str, Any]:
    """Compute updated parameters based on statistics.

    Args:
        current_params: Current params_base.yaml content.
        stats: Computed mode statistics.
        config: Update configuration.

    Returns:
        Updated params dict.
    """
    updated_params = current_params.copy()

    # Get current values
    payoff_mu_win = current_params.get("payoff_mu_win", {})
    payoff_mu_loss = current_params.get("payoff_mu_loss", {})

    # Supported modes
    modes = ["U", "S", "M", "L"]

    for mode in modes:
        mode_stats = stats.get(mode, ModeStats(mode=mode))

        # Check minimum trades requirement
        if mode_stats.n_trades < config.min_days_required:
            logger.info(
                f"Mode {mode}: {mode_stats.n_trades} trades < "
                f"min {config.min_days_required}, skipping update"
            )
            continue

        # Compute target values from stats
        target_win = mode_stats.avg_win_pct
        target_loss = mode_stats.avg_loss_pct

        # Get current values
        current_win = payoff_mu_win.get(mode, 0.04)
        current_loss = payoff_mu_loss.get(mode, 0.02)

        # Apply EWMA
        new_win = apply_ewma(current_win, target_win, config.ewma_alpha)
        new_loss = apply_ewma(current_loss, target_loss, config.ewma_alpha)

        # Apply bounds
        bounds = config.bounds
        new_win = clamp_value(new_win, bounds["mu_win"])
        new_loss = clamp_value(new_loss, bounds["mu_loss"])

        # Apply max change constraint
        max_win_change = current_win * config.max_change_per_run
        max_loss_change = current_loss * config.max_change_per_run

        new_win = max(current_win - max_win_change, min(current_win + max_win_change, new_win))
        new_loss = max(current_loss - max_loss_change, min(current_loss + max_loss_change, new_loss))

        # Update values
        payoff_mu_win[mode] = round(new_win, 4)
        payoff_mu_loss[mode] = round(new_loss, 4)

        logger.info(
            f"Mode {mode}: updated win={current_win:.4f}->{new_win:.4f}, "
            f"loss={current_loss:.4f}->{new_loss:.4f}"
        )

    # Update params
    updated_params["payoff_mu_win"] = payoff_mu_win
    updated_params["payoff_mu_loss"] = payoff_mu_loss

    return updated_params


def load_config(config_path: str) -> UpdateConfig:
    """Load auto_update configuration from YAML.

    Args:
        config_path: Path to params_base.yaml.

    Returns:
        UpdateConfig instance.
    """
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    auto_update = config_data.get("auto_update", {})

    return UpdateConfig(
        enabled=auto_update.get("enabled", True),
        min_days_required=auto_update.get("min_days_required", 7),
        ewma_alpha=auto_update.get("ewma_alpha", 0.15),
        bounds=auto_update.get("bounds", {
            "mu_win": [0.01, 0.25],
            "mu_loss": [0.005, 0.15],
            "p0": [0.52, 0.65],
            "delta0": [0.00, 0.04],
        }),
        max_change_per_run=auto_update.get("max_change_per_run", 0.20),
    )


def save_params(params: Dict[str, Any], output_path: str) -> None:
    """Save parameters to YAML file atomically.

    Args:
        params: Parameters dict.
        output_path: Output file path.
    """
    output_path = Path(output_path)

    # Write to temp file first
    temp_path = output_path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        yaml.dump(params, f, default_flow_style=False, sort_keys=False)

    # Rename to final location (atomic on POSIX)
    temp_path.replace(output_path)
    logger.info(f"Saved updated params to {output_path}")


def generate_summary(
    current_params: Dict[str, Any],
    updated_params: Dict[str, Any],
    stats: Dict[str, ModeStats],
) -> Dict[str, Any]:
    """Generate summary JSON for stdout.

    Args:
        current_params: Original params.
        updated_params: Updated params.
        stats: Computed statistics.

    Returns:
        Summary dict.
    """
    summary = {
        "updated": True,
        "modes": {},
    }

    for mode in ["U", "S", "M", "L"]:
        old_win = current_params.get("payoff_mu_win", {}).get(mode, 0)
        new_win = updated_params.get("payoff_mu_win", {}).get(mode, 0)
        old_loss = current_params.get("payoff_mu_loss", {}).get(mode, 0)
        new_loss = updated_params.get("payoff_mu_loss", {}).get(mode, 0)

        mode_stats = stats.get(mode, ModeStats(mode=mode))

        summary["modes"][mode] = {
            "trades": mode_stats.n_trades,
            "winrate": mode_stats.winrate,
            "payoff_mu_win": {
                "old": old_win,
                "new": new_win,
                "change": new_win - old_win,
            },
            "payoff_mu_loss": {
                "old": old_loss,
                "new": new_loss,
                "change": new_loss - old_loss,
            },
        }

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Update strategy parameters based on daily metrics"
    )
    parser.add_argument(
        "--metrics",
        required=True,
        help="Path to daily_metrics JSONL file",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to params_base.yaml",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for updated params",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output summary as JSON to stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print updates without writing file",
    )

    args = parser.parse_args()

    # Load configuration
    logger.info(f"Loading config from {args.config}")
    update_config = load_config(args.config)

    if not update_config.enabled:
        logger.info("Auto-update is disabled, exiting")
        if args.summary_json:
            print(json.dumps({"updated": False, "reason": "disabled"}))
        return 0

    # Load current params
    with open(args.config, "r") as f:
        current_params = yaml.safe_load(f)

    # Load metrics
    logger.info(f"Loading metrics from {args.metrics}")
    trades = load_metrics(args.metrics, args.lookback_days)

    if len(trades) == 0:
        logger.warning("No trades found, skipping update")
        if args.summary_json:
            print(json.dumps({"updated": False, "reason": "no_trades"}))
        return 0

    # Compute statistics
    stats = compute_mode_stats(trades)

    # Compute updated params
    updated_params = compute_updated_params(current_params, stats, update_config)

    # Output or save
    if args.dry_run:
        logger.info("Dry run - not writing file")
        print(yaml.dump(updated_params, default_flow_style=False, sort_keys=False))
    else:
        save_params(updated_params, args.output)

    # Summary JSON
    if args.summary_json:
        summary = generate_summary(current_params, updated_params, stats)
        print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
