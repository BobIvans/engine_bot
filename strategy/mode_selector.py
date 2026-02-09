"""strategy/mode_selector.py

PR-B.4 Dynamic Mode Selector - Pure Logic.

This module contains pure functions for dynamically selecting trading modes
(U, S, M, L) based on WalletProfile metrics and TokenSnapshot volatility.

No I/O operations - it reads from WalletProfile, TokenSnapshot, and config,
returns the selected mode string.

Modes:
- U: Ultra-fast scalper (15-30s hold)
- S: Fast scalper (60-90s hold)
- M: Medium scalper (120-180s hold)
- L: Long scalper (240-300s hold)
- *_aggr: Aggressive variants triggered by high volatility
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from integration.token_snapshot_store import TokenSnapshot
from integration.wallet_profile_store import WalletProfile


def select_mode(
    wallet_profile: Optional[WalletProfile],
    token_snapshot: Optional[TokenSnapshot],
    cfg: Dict[str, Any]
) -> Tuple[str, str]:
    """Select trading mode based on wallet behavior and token volatility.
    
    This is a pure function that:
    1. Determines base mode from wallet's median_hold_sec
    2. Optionally upgrades to aggressive variant based on volatility
    3. Returns mode string and selection reason
    
    Args:
        wallet_profile: WalletProfile with trading metrics (median_hold_sec)
        token_snapshot: TokenSnapshot with volatility data in extra["vol"]
        cfg: Strategy configuration dict with signals.modes settings
        
    Returns:
        Tuple of (mode: str, reason: str)
        mode: Selected mode string (e.g., "U", "S", "L_aggr")
        reason: Explanation for mode selection
    """
    # Get mode selection config
    modes_cfg = cfg.get("signals", {}).get("modes", {})
    choose_mode_cfg = modes_cfg.get("choose_mode", {})
    aggressive_cfg = modes_cfg.get("aggressive", {})
    
    # Default to 'U' if no config
    if not choose_mode_cfg:
        return ("U", "no_mode_config_default_U")
    
    # Step 1: Determine base mode from wallet median_hold_sec
    base_mode, base_reason = _select_base_mode(wallet_profile, choose_mode_cfg)
    
    # Step 2: Check for aggressive upgrade
    aggr_enabled = aggressive_cfg.get("enabled", False)
    if aggr_enabled:
        aggr_mode, aggr_reason = _check_aggressive_upgrade(
            base_mode=base_mode,
            base_reason=base_reason,
            token_snapshot=token_snapshot,
            aggressive_cfg=aggressive_cfg
        )
        if aggr_mode != base_mode:
            return (aggr_mode, aggr_reason)
    
    return (base_mode, base_reason)


def _select_base_mode(
    wallet_profile: Optional[WalletProfile],
    choose_mode_cfg: Dict[str, Any]
) -> Tuple[str, str]:
    """Select base mode from wallet median_hold_sec.
    
    Args:
        wallet_profile: WalletProfile with median_hold_sec
        choose_mode_cfg: Configuration with threshold settings
        
    Returns:
        Tuple of (mode: str, reason: str)
    """
    # Get thresholds
    u_threshold = choose_mode_cfg.get("U_if_median_hold_sec_lt", 40)
    s_threshold = choose_mode_cfg.get("S_if_median_hold_sec_lt", 100)
    m_threshold = choose_mode_cfg.get("M_if_median_hold_sec_lt", 220)
    else_mode = choose_mode_cfg.get("else_mode", "L")
    
    # Check if wallet profile has median_hold_sec
    if wallet_profile is None:
        return (else_mode, f"no_wallet_profile_default_{else_mode}")
    
    median_hold_sec = wallet_profile.median_hold_sec
    if median_hold_sec is None:
        return (else_mode, f"no_median_hold_sec_default_{else_mode}")
    
    # Select mode based on thresholds
    if median_hold_sec < u_threshold:
        return ("U", f"wallet_hold_{int(median_hold_sec)}s_implies_U")
    elif median_hold_sec < s_threshold:
        return ("S", f"wallet_hold_{int(median_hold_sec)}s_implies_S")
    elif median_hold_sec < m_threshold:
        return ("M", f"wallet_hold_{int(median_hold_sec)}s_implies_M")
    else:
        return (else_mode, f"wallet_hold_{int(median_hold_sec)}s_implies_{else_mode}")


def _check_aggressive_upgrade(
    base_mode: str,
    base_reason: str,
    token_snapshot: Optional[TokenSnapshot],
    aggressive_cfg: Dict[str, Any]
) -> Tuple[str, str]:
    """Check if aggressive upgrade is triggered.
    
    Args:
        base_mode: Selected base mode
        base_reason: Reason for base mode selection
        token_snapshot: TokenSnapshot with volatility data
        aggressive_cfg: Aggressive configuration with triggers
        
    Returns:
        Tuple of (mode: str, reason: str)
    """
    # Check if token snapshot is available
    if token_snapshot is None:
        return (base_mode, f"{base_reason} | no_snapshot_skip_aggressive")
    
    # Get volatility data from snapshot.extra["vol"]
    extra = token_snapshot.extra or {}
    vol_data = extra.get("vol", {})
    
    # Try to get price change percentage from various sources
    price_change_pct = _get_price_change_pct(vol_data, token_snapshot)
    
    if price_change_pct is None:
        return (base_mode, f"{base_reason} | no_vol_data_skip_aggressive")
    
    # Get triggers for the base mode
    triggers = aggressive_cfg.get("triggers", {})
    mode_triggers = triggers.get(base_mode, {})
    
    if not mode_triggers:
        return (base_mode, f"{base_reason} | no_aggr_trigger_for_{base_mode}")
    
    required_change = mode_triggers.get("require_price_change_pct", 0)
    within_sec = mode_triggers.get("within_sec", 60)
    
    # Check if price change meets threshold
    if abs(price_change_pct) >= required_change:
        aggr_mode = f"{base_mode}_aggr"
        return (aggr_mode, f"{base_reason} | aggr_triggered_{int(price_change_pct)}pct≥{int(required_change)}pct")
    
    return (base_mode, f"{base_reason} | aggr_not_triggered_{int(price_change_pct)}pct<{int(required_change)}pct")


def _get_price_change_pct(
    vol_data: Dict[str, Any],
    token_snapshot: TokenSnapshot
) -> Optional[float]:
    """Extract price change percentage from volatility data.
    
    Args:
        vol_data: Volatility data dict
        token_snapshot: TokenSnapshot for fallback
        
    Returns:
        Optional[float] price change percentage
    """
    # Try various sources for price change data
    
    # 1. Try vol_data["ret_30s"] (return in 30 seconds)
    ret_30s = vol_data.get("ret_30s")
    if ret_30s is not None:
        try:
            return float(ret_30s)
        except (ValueError, TypeError):
            pass
    
    # 2. Try token_snapshot extra for direct price change
    extra = token_snapshot.extra or {}
    price_change = extra.get("price_change_pct")
    if price_change is not None:
        try:
            return float(price_change)
        except (ValueError, TypeError):
            pass
    
    # 3. Try extra["vol"]["price_change_30s"]
    price_change_30s = extra.get("vol", {}).get("price_change_30s")
    if price_change_30s is not None:
        try:
            return float(price_change_30s)
        except (ValueError, TypeError):
            pass
    
    return None


def select_mode_simple(
    median_hold_sec: Optional[float],
    cfg: Dict[str, Any]
) -> Tuple[str, str]:
    """Simplified mode selection for testing without full profile/snapshot.
    
    Args:
        median_hold_sec: Wallet's median hold time in seconds
        cfg: Strategy configuration dict
        
    Returns:
        Tuple of (mode: str, reason: str)
    """
    # Create a minimal config structure for the simplified function
    class _MockProfile:
        def __init__(self, hold_sec):
            self.median_hold_sec = hold_sec
    
    mock_profile = _MockProfile(median_hold_sec) if median_hold_sec is not None else None
    return select_mode(mock_profile, None, cfg)
