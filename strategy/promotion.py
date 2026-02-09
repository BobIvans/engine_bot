"""strategy/promotion.py

Pure logic for daily wallet pruning and promotion.

This module provides deterministic functions for:
- Pruning underperforming wallets from the Active Universe
- Promoting high-quality candidates to the Active Universe
- Maintaining the Active Universe quality threshold

All functions are pure (no I/O) for testability.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

# Import reject reasons from integration
import sys
sys.path.insert(0, '.')
try:
    from integration.reject_reasons import (
        WALLET_WINRATE_7D_LOW,
        WALLET_TRADES_7D_LOW,
        WALLET_ROI_7D_LOW,
    )
except ImportError:
    # Fallback for standalone testing
    WALLET_WINRATE_7D_LOW = "wallet_winrate_7d_low"
    WALLET_TRADES_7D_LOW = "wallet_trades_7d_low"
    WALLET_ROI_7D_LOW = "wallet_roi_7d_low"


@dataclass
class WalletProfileInput:
    """Minimal wallet profile for promotion/pruning decisions."""
    wallet: str
    winrate_7d: Optional[float] = None
    roi_7d: Optional[float] = None
    trades_7d: Optional[int] = None
    winrate_30d: Optional[float] = None
    roi_30d: Optional[float] = None
    trades_30d: Optional[int] = None
    last_active_ts: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet": self.wallet,
            "winrate_7d": self.winrate_7d,
            "roi_7d": self.roi_7d,
            "trades_7d": self.trades_7d,
            "winrate_30d": self.winrate_30d,
            "roi_30d": self.roi_30d,
            "trades_30d": self.trades_30d,
            "last_active_ts": self.last_active_ts,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WalletProfileInput":
        return cls(
            wallet=data.get("wallet", ""),
            winrate_7d=data.get("winrate_7d"),
            roi_7d=data.get("roi_7d"),
            trades_7d=data.get("trades_7d"),
            winrate_30d=data.get("winrate_30d"),
            roi_30d=data.get("roi_30d"),
            trades_30d=data.get("trades_30d"),
            last_active_ts=data.get("last_active_ts"),
        )


@dataclass
class PromotionParams:
    """Configuration parameters for pruning and promotion."""
    # Pruning thresholds (wallets below these are removed)
    prune_winrate_7d_min: float = 0.55
    prune_trades_7d_min: int = 8
    prune_roi_7d_min: float = -0.10  # Allow small negative ROI
    
    # Promotion thresholds (candidates above these can be promoted)
    promote_min_winrate_30d: float = 0.62
    promote_min_roi_30d: float = 0.18
    promote_min_trades_30d: int = 45
    promote_max_candidates: int = 30


@dataclass
class PruningResult:
    """Result of a pruning decision for a single wallet."""
    wallet: str
    kept: bool
    reason: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


@dataclass
class PromotionResult:
    """Result of a promotion decision for a single candidate."""
    wallet: str
    promoted: bool
    reason: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


@dataclass
class DailyPromotionOutput:
    """Complete output of daily_prune_and_promote()."""
    remaining_active: List[WalletProfileInput]
    pruned_wallets: List[Dict[str, Any]]
    promoted_wallets: List[WalletProfileInput]
    rejected_candidates: List[Dict[str, Any]]
    summary: Dict[str, int]


def daily_prune_and_promote(
    active_profiles: List[WalletProfileInput],
    candidate_profiles: List[WalletProfileInput],
    params: PromotionParams,
) -> Tuple[List[WalletProfileInput], List[Dict[str, Any]]]:
    """
    Perform daily pruning and promotion of wallets.
    
    Args:
        active_profiles: Current active wallet profiles
        candidate_profiles: Candidate wallets for promotion
        params: Configuration parameters for thresholds
    
    Returns:
        Tuple of (remaining_active_wallets, pruned_wallets_with_reasons)
    
    The function:
    1. Prunes underperforming wallets from active set
    2. Promotes qualified candidates to active set
    3. Returns remaining active + list of pruned wallets with reasons
    """
    # Step 1: Prune underperforming active wallets
    remaining_active: List[WalletProfileInput] = []
    pruned_wallets: List[Dict[str, Any]] = []
    
    for wallet in active_profiles:
        result = _evaluate_prune(wallet, params)
        if result.kept:
            remaining_active.append(wallet)
        else:
            pruned_wallets.append({
                "wallet": result.wallet,
                "reason": result.reason,
                "metrics": result.metrics,
            })
    
    # Step 2: Filter candidates by promotion criteria
    qualified_candidates: List[WalletProfileInput] = []
    rejected_candidates: List[Dict[str, Any]] = []
    
    for candidate in candidate_profiles:
        result = _evaluate_promotion(candidate, params)
        if result.promoted:
            qualified_candidates.append(candidate)
        else:
            rejected_candidates.append({
                "wallet": result.wallet,
                "reason": result.reason,
                "metrics": result.metrics,
            })
    
    # Step 3: Limit number of promotions
    # Sort by winrate_30d descending to pick best candidates first
    qualified_candidates.sort(
        key=lambda w: w.winrate_30d if w.winrate_30d else 0.0,
        reverse=True
    )
    
    # Take top N candidates
    max_promote = params.promote_max_candidates
    promoted_wallets = qualified_candidates[:max_promote]
    
    # Step 4: Build final active set
    final_active = remaining_active + promoted_wallets
    
    return final_active, pruned_wallets


def _evaluate_prune(
    wallet: WalletProfileInput,
    params: PromotionParams,
) -> PruningResult:
    """Evaluate if a wallet should be pruned from active set."""
    reasons: List[str] = []
    metrics = {
        "winrate_7d": wallet.winrate_7d,
        "roi_7d": wallet.roi_7d,
        "trades_7d": wallet.trades_7d,
    }
    
    # Check winrate threshold
    if wallet.winrate_7d is not None and wallet.winrate_7d < params.prune_winrate_7d_min:
        reasons.append(f"winrate_7d={wallet.winrate_7d:.2f} < {params.prune_winrate_7d_min}")
    
    # Check trades threshold
    if wallet.trades_7d is not None and wallet.trades_7d < params.prune_trades_7d_min:
        reasons.append(f"trades_7d={wallet.trades_7d} < {params.prune_trades_7d_min}")
    
    # Check ROI threshold (only if both ROI and trades are available)
    if wallet.roi_7d is not None and wallet.trades_7d is not None:
        if wallet.roi_7d < params.prune_roi_7d_min:
            reasons.append(f"roi_7d={wallet.roi_7d:.2%} < {params.prune_roi_7d_min:.2%}")
    
    if reasons:
        # Determine primary reason for rejection
        primary_reason = _determine_prune_reason(wallet, params)
        return PruningResult(
            wallet=wallet.wallet,
            kept=False,
            reason=primary_reason,
            metrics=metrics,
        )
    
    return PruningResult(wallet=wallet.wallet, kept=True, metrics=metrics)


def _determine_prune_reason(
    wallet: WalletProfileInput,
    params: PromotionParams,
) -> str:
    """Determine the primary reason for pruning a wallet."""
    # Priority: winrate > trades > ROI
    if wallet.winrate_7d is not None and wallet.winrate_7d < params.prune_winrate_7d_min:
        return WALLET_WINRATE_7D_LOW
    if wallet.trades_7d is not None and wallet.trades_7d < params.prune_trades_7d_min:
        return WALLET_TRADES_7D_LOW
    return WALLET_ROI_7D_LOW


def _evaluate_promotion(
    candidate: WalletProfileInput,
    params: PromotionParams,
) -> PromotionResult:
    """Evaluate if a candidate should be promoted to active set."""
    reasons: List[str] = []
    metrics = {
        "winrate_30d": candidate.winrate_30d,
        "roi_30d": candidate.roi_30d,
        "trades_30d": candidate.trades_30d,
    }
    
    # All metrics are required for promotion (strict criteria)
    if candidate.winrate_30d is None:
        reasons.append("winrate_30d is None")
    elif candidate.winrate_30d < params.promote_min_winrate_30d:
        reasons.append(f"winrate_30d={candidate.winrate_30d:.2f} < {params.promote_min_winrate_30d}")
    
    if candidate.roi_30d is None:
        reasons.append("roi_30d is None")
    elif candidate.roi_30d < params.promote_min_roi_30d:
        reasons.append(f"roi_30d={candidate.roi_30d:.2%} < {params.promote_min_roi_30d:.2%}")
    
    if candidate.trades_30d is None:
        reasons.append("trades_30d is None")
    elif candidate.trades_30d < params.promote_min_trades_30d:
        reasons.append(f"trades_30d={candidate.trades_30d} < {params.promote_min_trades_30d}")
    
    if reasons:
        return PromotionResult(
            wallet=candidate.wallet,
            promoted=False,
            reason="; ".join(reasons),
            metrics=metrics,
        )
    
    return PromotionResult(wallet=candidate.wallet, promoted=True, metrics=metrics)


def create_promotion_params_from_config(config: Dict[str, Any]) -> PromotionParams:
    """Create PromotionParams from config dict."""
    prune_cfg = (config.get("prune") or {})
    promote_cfg = (config.get("promote") or {})
    
    return PromotionParams(
        prune_winrate_7d_min=prune_cfg.get("winrate_7d_min", 0.55),
        prune_trades_7d_min=prune_cfg.get("min_trades_7d", 8),
        prune_roi_7d_min=prune_cfg.get("roi_7d_min", -0.10),
        promote_min_winrate_30d=promote_cfg.get("min_winrate_30d", 0.62),
        promote_min_roi_30d=promote_cfg.get("min_roi_30d", 0.18),
        promote_min_trades_30d=promote_cfg.get("min_trades_30d", 45),
        promote_max_candidates=promote_cfg.get("max_candidates_to_promote", 30),
    )


if __name__ == "__main__":
    # Quick self-test
    print("Promotion Logic Self-Test")
    print("=" * 40)
    
    # Test data
    active = [
        WalletProfileInput(wallet="wallet_good", winrate_7d=0.65, trades_7d=20, roi_7d=0.15),
        WalletProfileInput(wallet="wallet_bad", winrate_7d=0.40, trades_7d=5, roi_7d=-0.25),
        WalletProfileInput(wallet="wallet_marginal", winrate_7d=0.58, trades_7d=3, roi_7d=0.05),
    ]
    
    candidates = [
        WalletProfileInput(wallet="candidate_excellent", winrate_30d=0.75, trades_30d=100, roi_30d=0.35),
        WalletProfileInput(wallet="candidate_poor", winrate_30d=0.45, trades_30d=20, roi_30d=0.05),
        WalletProfileInput(wallet="candidate_qualified", winrate_30d=0.68, trades_30d=60, roi_30d=0.22),
    ]
    
    params = PromotionParams()
    
    remaining, pruned = daily_prune_and_promote(active, candidates, params)
    
    print(f"Remaining active: {[w.wallet for w in remaining]}")
    print(f"Pruned: {[p['wallet'] for p in pruned]}")
    
    for p in pruned:
        print(f"  - {p['wallet']}: {p['reason']}")
