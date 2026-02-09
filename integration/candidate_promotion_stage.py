#!/usr/bin/env python3
"""integration/candidate_promotion_stage.py

PR-H.3: Wallet Pruning & Promotion Stage

Glue layer that:
- Reads current Active Universe from wallet_profile_store
- Reads candidate wallets from discovery/source
- Calls pure promotion logic from strategy/promotion.py
- Saves updated Active Universe
- Logs pruned wallets with reasons
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .reject_reasons import (
    WALLET_WINRATE_7D_LOW,
    WALLET_TRADES_7D_LOW,
    WALLET_ROI_7D_LOW,
    assert_reason_known,
)

# Import pure promotion logic
from strategy.promotion import (
    daily_prune_and_promote,
    WalletProfileInput,
    PromotionParams,
    create_promotion_params_from_config,
)

logger = logging.getLogger(__name__)


def load_wallet_profiles_from_csv(
    path: str,
) -> List[WalletProfileInput]:
    """Load wallet profiles from CSV file."""
    profiles: List[WalletProfileInput] = []
    
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = WalletProfileInput(
                wallet=row.get("wallet", ""),
                winrate_7d=_parse_float(row.get("winrate_7d")),
                roi_7d=_parse_float(row.get("roi_7d")),
                trades_7d=_parse_int(row.get("trades_7d")),
                winrate_30d=_parse_float(row.get("winrate_30d")),
                roi_30d=_parse_float(row.get("roi_30d")),
                trades_30d=_parse_int(row.get("trades_30d")),
                last_active_ts=row.get("last_active_ts"),
            )
            if profile.wallet:
                profiles.append(profile)
    
    return profiles


def save_wallet_profiles_to_csv(
    profiles: List[WalletProfileInput],
    path: str,
) -> None:
    """Save wallet profiles to CSV file."""
    fieldnames = [
        "wallet", "winrate_7d", "roi_7d", "trades_7d",
        "winrate_30d", "roi_30d", "trades_30d", "last_active_ts",
    ]
    
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for profile in profiles:
            row = {
                "wallet": profile.wallet,
                "winrate_7d": _format_float(profile.winrate_7d),
                "roi_7d": _format_float(profile.roi_7d),
                "trades_7d": _format_int(profile.trades_7d),
                "winrate_30d": _format_float(profile.winrate_30d),
                "roi_30d": _format_float(profile.roi_30d),
                "trades_30d": _format_int(profile.trades_30d),
                "last_active_ts": profile.last_active_ts or "",
            }
            writer.writerow(row)


def load_config(path: str = "strategy/config/params_base.yaml") -> Dict[str, Any]:
    """Load promotion config from YAML file."""
    import yaml
    
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    promotion_cfg = config.get("promotion", {})
    return promotion_cfg


def run_promotion_stage(
    active_csv: str,
    candidates_csv: str,
    output_csv: str,
    config: Dict[str, Any],
    dry_run: bool = False,
    skip_save: bool = False,
) -> Dict[str, Any]:
    """
    Run the wallet promotion/pruning stage.
    
    Args:
        active_csv: Path to active wallets CSV
        candidates_csv: Path to candidate wallets CSV
        output_csv: Path to save updated active wallets
        config: Promotion configuration dict
        dry_run: If True, don't save changes
        skip_save: If True, only run logic without saving
    
    Returns:
        Dict with stage results for summary
    """
    # Validate reject reasons
    for reason in [WALLET_WINRATE_7D_LOW, WALLET_TRADES_7D_LOW, WALLET_ROI_7D_LOW]:
        assert_reason_known(reason)
    
    logger.info(f"[promotion_stage] Loading active wallets from {active_csv}")
    active_profiles = load_wallet_profiles_from_csv(active_csv)
    logger.info(f"[promotion_stage] Loaded {len(active_profiles)} active wallets")
    
    logger.info(f"[promotion_stage] Loading candidates from {candidates_csv}")
    candidate_profiles = load_wallet_profiles_from_csv(candidates_csv)
    logger.info(f"[promotion_stage] Loaded {len(candidate_profiles)} candidates")
    
    # Create promotion params from config
    params = create_promotion_params_from_config(config)
    logger.info(f"[promotion_stage] Using params: prune_winrate_7d_min={params.prune_winrate_7d_min}, "
                f"promote_min_winrate_30d={params.promote_min_winrate_30d}")
    
    # Run pure promotion logic
    logger.info("[promotion_stage] Running daily_prune_and_promote...")
    remaining_active, pruned_wallets = daily_prune_and_promote(
        active_profiles=active_profiles,
        candidate_profiles=candidate_profiles,
        params=params,
    )
    
    logger.info(f"[promotion_stage] Result: {len(remaining_active)} remaining, "
                f"{len(pruned_wallets)} pruned")
    
    # Build output
    promoted_wallets = [w for w in remaining_active if w not in active_profiles]
    rejected_candidates = [c for c in candidate_profiles if c not in promoted_wallets]
    
    # Filter out wallets that weren't in original active
    original_wallets = {w.wallet for w in active_profiles}
    actual_promoted = [w for w in promoted_wallets if w.wallet not in original_wallets]
    actual_rejected = [c for c in rejected_candidates if c.wallet not in original_wallets]
    
    # Log pruned wallets
    for pruned in pruned_wallets:
        logger.info(f"[promotion_stage] PRUNED: wallet={pruned['wallet']}, "
                    f"reason={pruned['reason']}")
    
    # Log promoted wallets
    for promoted in actual_promoted:
        logger.info(f"[promotion_stage] PROMOTED: wallet={promoted.wallet}")
    
    # Save if not dry run
    if not dry_run and not skip_save:
        logger.info(f"[promotion_stage] Saving updated active wallets to {output_csv}")
        save_wallet_profiles_to_csv(remaining_active, output_csv)
    elif dry_run:
        logger.info("[promotion_stage] Dry run - not saving changes")
    
    # Return summary for JSON output
    return {
        "remaining_active_count": len(remaining_active),
        "pruned_count": len(pruned_wallets),
        "promoted_count": len(actual_promoted),
        "rejected_candidates_count": len(actual_rejected),
        "pruned_wallets": pruned_wallets,
        "promoted_wallets": [w.to_dict() for w in actual_promoted],
    }


def _parse_float(value: Optional[str]) -> Optional[float]:
    """Parse float from string, return None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    """Parse int from string, return None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _format_float(value: Optional[float]) -> str:
    """Format float for CSV output."""
    if value is None:
        return ""
    return f"{value:.4f}"


def _format_int(value: Optional[int]) -> str:
    """Format int for CSV output."""
    if value is None:
        return ""
    return str(value)


def main() -> int:
    """CLI entry point for promotion stage."""
    parser = argparse.ArgumentParser(description="Wallet Pruning & Promotion Stage")
    parser.add_argument("--active-csv", required=True)
    parser.add_argument("--candidates-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--config", default="strategy/config/params_base.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-save", action="store_true")
    parser.add_argument("--summary-json", action="store_true")
    
    args = parser.parse_args()
    
    # Load config
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"[promotion_stage] Failed to load config: {e}")
        return 1
    
    # Run stage
    result = run_promotion_stage(
        active_csv=args.active_csv,
        candidates_csv=args.candidates_csv,
        output_csv=args.output_csv,
        config=config,
        dry_run=args.dry_run,
        skip_save=args.skip_save,
    )
    
    # Output JSON summary if requested
    if args.summary_json:
        print(json.dumps(result, ensure_ascii=False))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
