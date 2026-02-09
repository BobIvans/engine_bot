"""
Pure logic for Wallet Tier Auto-Scaling.

Analyzes copy-trading wallet performance and recommends tier changes:
- PROMOTE: Move high-performing candidates to Tier 1
- DEMOTE: Move underperforming leaders to lower tiers
- FIRE: Remove persistently bad wallets

Input: Current tier config, Performance metrics
Output: List of recommended changes (Action, Reason)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum


class TierAction(Enum):
    """Actions for tier management."""
    PROMOTE = "PROMOTE"  # Upgrade tier (e.g. 2 -> 1)
    DEMOTE = "DEMOTE"    # Downgrade tier (e.g. 1 -> 3)
    KEEP = "KEEP"        # No change
    FIRE = "FIRE"        # Remove from tracking


@dataclass
class TierChange:
    """Recommended change for a single wallet."""
    wallet: str
    current_tier: str
    new_tier: str
    action: str
    reason: str
    metrics: Dict[str, float]
    
    def to_dict(self) -> dict:
        return {
            "wallet": self.wallet,
            "current_tier": self.current_tier,
            "new_tier": self.new_tier,
            "action": self.action,
            "reason": self.reason,
            "metrics": self.metrics,
        }


@dataclass
class AutoscalingResult:
    """Result of the autoscaling process."""
    changes: List[TierChange]
    new_config: Dict[str, List[str]]
    
    def get_change_log(self) -> List[dict]:
        return [c.to_dict() for c in self.changes]


# Default configuration
DEFAULT_PARAMS = {
    "min_roi_promote": 0.20,      # 20% ROI to promote
    "min_winrate_promote": 0.60,  # 60% WR to promote
    "max_roi_demote": -0.15,      # -15% ROI to demote
    "max_winrate_demote": 0.30,   # 30% WR to demote
    "target_tier1_size": 50,      # Desired size of Tier 1
    "whitelist": [],              # Wallets to never touch
}


def calculate_tier_changes(
    current_tiers: Dict[str, List[str]],
    metrics_list: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None
) -> AutoscalingResult:
    """
    Calculate recommended tier changes based on performance metrics.
    
    Args:
        current_tiers: Dict mapping tier name to list of wallet addresses
                       e.g. {"tier_1": ["addr1", ...], "tier_2": [...]}
        metrics_list: List of dicts with wallet metrics (roi_7d, winrate, etc.)
        params: Configuration parameters (thresholds, limits)
        
    Returns:
        AutoscalingResult containing individual changes and the new config structure
    """
    if params is None:
        params = DEFAULT_PARAMS
    else:
        # Merge provided params with defaults
        combined = DEFAULT_PARAMS.copy()
        combined.update(params)
        params = combined
        
    # Index metrics by wallet for easy lookup
    metrics_map = {m["wallet"]: m for m in metrics_list}
    
    # Track current state
    tier1 = set(current_tiers.get("tier_1", []))
    tier2 = set(current_tiers.get("tier_2", []))
    tier3 = set(current_tiers.get("tier_3", []))
    
    all_known_wallets = tier1 | tier2 | tier3
    
    changes: List[TierChange] = []
    
    # 1. Process Demotions (Tier 1 -> Tier 3)
    # Rules: ROI < -15% OR Winrate < 30%
    tier1_candidates = list(tier1)
    for wallet in tier1_candidates:
        if wallet in params.get("whitelist", []):
            continue
            
        metrics = metrics_map.get(wallet)
        if not metrics:
            continue
            
        roi = metrics.get("roi_7d", 0.0)
        winrate = metrics.get("winrate", 0.0)
        
        should_demote = False
        reason = ""
        
        if roi < params["max_roi_demote"]:
            should_demote = True
            reason = f"Low ROI ({roi*100:.1f}% < {params['max_roi_demote']*100:.1f}%)"
        elif winrate < params["max_winrate_demote"]:
            should_demote = True
            reason = f"Low Winrate ({winrate*100:.1f}% < {params['max_winrate_demote']*100:.1f}%)"
            
        if should_demote:
            changes.append(TierChange(
                wallet=wallet,
                current_tier="tier_1",
                new_tier="tier_3",
                action=TierAction.DEMOTE.value,
                reason=reason,
                metrics={"roi": roi, "winrate": winrate}
            ))
            tier1.remove(wallet)
            tier3.add(wallet)
            
    # 2. Process Promotions (Tier 2/3 -> Tier 1)
    # Rules: ROI > 20% AND Winrate > 60%
    candidates_pool = list(tier2 | tier3)
    promoted_candidates = []
    
    for wallet in candidates_pool:
        metrics = metrics_map.get(wallet)
        if not metrics:
            continue
            
        roi = metrics.get("roi_7d", 0.0)
        winrate = metrics.get("winrate", 0.0)
        current_tier = "tier_2" if wallet in tier2 else "tier_3"
        
        if roi > params["min_roi_promote"] and winrate > params["min_winrate_promote"]:
            # Candidate fits criteria
            promoted_candidates.append({
                "wallet": wallet,
                "roi": roi,
                "winrate": winrate,
                "current_tier": current_tier
            })
    
    # Sort candidates by combined score (simple avg of roi and winrate for now)
    # This helps pick the BEST candidates if we have limited slots
    promoted_candidates.sort(key=lambda x: x["roi"] + x["winrate"], reverse=True)
    
    # Apply promotions respecting max size (optional extension, currently just promote all qualifying)
    # In a real system we might limit how many we promote at once
    for cand in promoted_candidates:
        wallet = cand["wallet"]
        changes.append(TierChange(
            wallet=wallet,
            current_tier=cand["current_tier"],
            new_tier="tier_1",
            action=TierAction.PROMOTE.value,
            reason=f"High Performance (ROI {cand['roi']*100:.1f}%, WR {cand['winrate']*100:.1f}%)",
            metrics={"roi": cand["roi"], "winrate": cand["winrate"]}
        ))
        
        if wallet in tier2:
            tier2.remove(wallet)
        elif wallet in tier3:
            tier3.remove(wallet)
        tier1.add(wallet)
        
    # 3. Size Constraint Check (Tier 1)
    # If Tier 1 is too big, demote worst performers (lowest ROI)
    target_size = params["target_tier1_size"]
    extra_count = len(tier1) - target_size
    
    if extra_count > 0:
        # Sort Tier 1 by ROI to find worst
        tier1_sorted = []
        for wallet in tier1:
            if wallet in params.get("whitelist", []):
                continue
            
            m = metrics_map.get(wallet, {"roi_7d": 0.0})
            tier1_sorted.append((wallet, m.get("roi_7d", 0.0)))
            
        tier1_sorted.sort(key=lambda x: x[1])  # Ascending ROI
        
        # Remove worst N
        to_remove = tier1_sorted[:extra_count]
        for wallet, roi in to_remove:
            changes.append(TierChange(
                wallet=wallet,
                current_tier="tier_1",
                new_tier="tier_2", # Soft landing to Tier 2
                action=TierAction.DEMOTE.value,
                reason=f"Size Constraint (Lowest ROI {roi*100:.1f}%)",
                metrics={"roi": roi, "winrate": metrics_map.get(wallet, {}).get("winrate", 0.0)}
            ))
            tier1.remove(wallet)
            tier2.add(wallet)

    # Reconstruct config
    new_config = {
        "tier_1": sorted(list(tier1)),
        "tier_2": sorted(list(tier2)),
        "tier_3": sorted(list(tier3)),
    }
    
    return AutoscalingResult(
        changes=changes,
        new_config=new_config
    )
