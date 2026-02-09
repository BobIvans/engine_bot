#!/usr/bin/env python3
"""integration/candidate_promotion.py

PR-H.2 Candidate Evaluation & Promotion Logic.

CLI utility for promoting wallets from 'candidate' to 'tier2' based on
paper trading simulation metrics. Promotes only wallets that meet tier2
thresholds from config.

Usage:
    python -m integration.candidate_promotion \
        --profiles integration/fixtures/promotion/wallet_profiles_candidates.csv \
        --metrics integration/fixtures/promotion/sim_metrics_by_wallet.json \
        --output integration/fixtures/promotion/promoted_output.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, TextIO


@dataclass
class PromotionResult:
    """Result of a single wallet promotion decision."""
    wallet: str
    old_tier: str
    new_tier: str
    reason: str


@dataclass
class PromotionSummary:
    """Summary statistics for promotion run."""
    total_candidates: int = 0
    promoted_count: int = 0
    results: List[PromotionResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "promoted_count": self.promoted_count,
        }


def load_config_thresholds(config_path: str) -> Dict[str, Any]:
    """Load tier2 thresholds from config file."""
    from integration.config_loader import load_params_base

    loaded = load_params_base(config_path)
    tiering = loaded.config.get("wallet_profile", {}).get("tiering", {})
    tier2_config = tiering.get("tier2", {})

    return {
        "min_roi_30d_pct": tier2_config.get("min_roi_30d_pct", 0.0),
        "min_winrate_30d": tier2_config.get("min_winrate_30d", 0.0),
        "min_trades_30d": tier2_config.get("min_trades_30d", 0),
    }


def load_candidate_profiles(profiles_path: str) -> List[Dict[str, Any]]:
    """Load wallet profiles and filter to only candidates."""
    candidates = []

    with open(profiles_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tier = row.get("tier", "").strip().lower()
            if tier == "candidate":
                candidates.append(row)

    return candidates


def load_metrics(metrics_path: str) -> Dict[str, Dict[str, Any]]:
    """Load simulation metrics from JSON file."""
    with open(metrics_path, 'r') as f:
        data = json.load(f)

    # Handle both dict and list formats
    if isinstance(data, list):
        metrics = {}
        for item in data:
            wallet = item.get("wallet")
            if wallet:
                metrics[wallet] = item
        return metrics

    return data


def evaluate_promotion(
    wallet: str,
    metrics: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate if a wallet should be promoted to tier2.

    Returns:
        Tuple of (should_promote: bool, reason: str)
    """
    # Get metrics with fallbacks
    roi = 0.0
    winrate = 0.0
    trades = 0

    # Handle various metric key names
    roi_key = "roi_30d_pct"
    winrate_key = "winrate_30d"
    trades_key = "trades_30d"

    # Try multiple key variations
    roi = float(metrics.get(roi_key, 0) or
                metrics.get("sim_roi", 0) or
                metrics.get("roi", 0) or 0)
    winrate = float(metrics.get(winrate_key, 0) or
                    metrics.get("winrate", 0) or 0)
    trades = int(metrics.get(trades_key, 0) or
                 metrics.get("trades", 0) or 0)

    min_roi = thresholds["min_roi_30d_pct"]
    min_winrate = thresholds["min_winrate_30d"]
    min_trades = thresholds["min_trades_30d"]

    # Check all conditions
    failures = []

    if roi < min_roi:
        failures.append(f"roi={roi:.1f}% < {min_roi}%")
    if winrate < min_winrate:
        failures.append(f"winrate={winrate:.2f} < {min_winrate:.2f}")
    if trades < min_trades:
        failures.append(f"trades={trades} < {min_trades}")

    if failures:
        return False, "; ".join(failures)

    return True, f"roi={roi:.1f}% >= {min_roi}%, winrate={winrate:.2f} >= {min_winrate:.2f}, trades={trades} >= {min_trades}"


def run_promotion(
    profiles_path: str,
    metrics_path: str,
    config_path: str = "strategy/config/params_base.yaml",
) -> PromotionSummary:
    """Run the promotion evaluation pipeline.

    Args:
        profiles_path: Path to CSV file with wallet profiles.
        metrics_path: Path to JSON file with simulation metrics.
        config_path: Path to strategy config file.

    Returns:
        PromotionSummary with results.
    """
    # Load config thresholds
    thresholds = load_config_thresholds(config_path)

    # Load candidate profiles
    candidates = load_candidate_profiles(profiles_path)

    # Load metrics
    metrics_map = load_metrics(metrics_path)

    summary = PromotionSummary(total_candidates=len(candidates))

    for candidate in candidates:
        wallet = candidate.get("wallet", "").strip()

        if not wallet:
            continue

        # Get metrics for this wallet
        wallet_metrics = metrics_map.get(wallet, {})

        if not wallet_metrics:
            # Skip if no metrics available
            continue

        # Evaluate promotion
        should_promote, reason = evaluate_promotion(wallet, wallet_metrics, thresholds)

        if should_promote:
            result = PromotionResult(
                wallet=wallet,
                old_tier="candidate",
                new_tier="tier2",
                reason=reason,
            )
            summary.results.append(result)
            summary.promoted_count += 1

    return summary


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Candidate Promotion: Evaluate and promote candidate wallets to tier2"
    )
    parser.add_argument(
        "--profiles",
        required=True,
        help="Path to CSV file with wallet profiles",
    )
    parser.add_argument(
        "--metrics",
        required=True,
        help="Path to JSON file with simulation metrics",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output JSON file for promoted wallets",
    )
    parser.add_argument(
        "--config",
        default="strategy/config/params_base.yaml",
        help="Path to strategy config file (default: strategy/config/params_base.yaml)",
    )

    args = parser.parse_args()

    # Run promotion
    summary = run_promotion(
        profiles_path=args.profiles,
        metrics_path=args.metrics,
        config_path=args.config,
    )

    # Write output
    output_data = [
        {
            "wallet": r.wallet,
            "old_tier": r.old_tier,
            "new_tier": r.new_tier,
            "reason": r.reason,
        }
        for r in summary.results
    ]

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    # Print summary to stdout
    print(json.dumps(summary.to_dict()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
