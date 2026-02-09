"""strategy/risk_engine.py

Risk engine (P0): position sizing + kill-switch.

Design goals:
- Pure functions (deterministic, easy to unit test)
- No external dependencies
- Uses strategy/config/params_base.yaml settings
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from integration.portfolio_stub import PortfolioStub
from integration.reject_reasons import (
    RISK_COOLDOWN,
    RISK_KILL_SWITCH,
    RISK_MAX_EXPOSURE,
    RISK_MAX_POSITIONS,
    RISK_MODE_LIMIT,
    RISK_WALLET_TIER_LIMIT,
    assert_reason_known,
)
from integration.trade_types import Trade
from strategy.regime import adjust_position_size


def _check_tier_limits(
    *,
    trade: Trade,
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Check wallet tier position limits.

    Args:
        trade: The trade to evaluate
        portfolio: Current portfolio state
        cfg: Strategy configuration dict

    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
    """
    # Extract tier from trade.extra (may be None if not pre-computed)
    # Handle both Trade objects and dicts for backward compatibility
    if hasattr(trade, 'extra'):
        extra = trade.extra or {}
    elif isinstance(trade, dict):
        extra = trade.get('extra', {}) or {}
    else:
        extra = {}
    tier = extra.get('wallet_tier')

    # Handle tier=None case with fallback config
    risk = (cfg.get("risk") or {})
    limits = (risk.get("limits") or {})
    tier_limits = (limits.get("tier_limits") or {})

    if tier is None:
        # Apply fallback (strict) limits or skip based on config
        fallback_action = tier_limits.get("fallback_action", "strict")  # "strict" or "skip"
        if fallback_action == "skip":
            return True, None
        # Strict mode: use fallback limit, only if explicitly configured
        fallback_limit = tier_limits.get("fallback_max_positions")
        if fallback_limit is None:
            # No fallback_max_positions configured, allow the trade
            return True, None
        if portfolio.open_positions >= fallback_limit:
            reason = RISK_WALLET_TIER_LIMIT
            assert_reason_known(reason)
            return False, reason
        return True, None

    # Get tier-specific limits
    tier_config = tier_limits.get(tier, {})
    max_open_positions = tier_config.get("max_open_positions")

    if max_open_positions is None:
        # Tier exists but no specific limit configured - allow by default
        return True, None

    # Check against tier-specific limit
    current_count = portfolio.active_counts_by_tier.get(tier, 0)
    if current_count >= max_open_positions:
        reason = RISK_WALLET_TIER_LIMIT
        assert_reason_known(reason)
        return False, reason

    return True, None


def _check_mode_limits(
    *,
    trade: Trade,
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Check mode-based position limits.

    Args:
        trade: The trade to evaluate
        portfolio: Current portfolio state
        cfg: Strategy configuration dict

    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
    """
    # Extract mode from trade.extra (may be None if not pre-computed)
    # Handle both Trade objects and dicts for backward compatibility
    if hasattr(trade, 'extra'):
        extra = trade.extra or {}
    elif isinstance(trade, dict):
        extra = trade.get('extra', {}) or {}
    else:
        extra = {}
    mode = extra.get('mode', 'U')  # Default to 'U' if None

    # Get trade size in USD
    # Handle both Trade objects and dicts
    if hasattr(trade, 'size_usd'):
        trade_size = trade.size_usd or 0.0
    elif isinstance(trade, dict):
        trade_size = trade.get('size_usd', 0.0) or 0.0
    else:
        trade_size = 0.0

    # Get mode limits from config
    risk = (cfg.get("risk") or {})
    limits = (risk.get("limits") or {})
    mode_limits = (limits.get("modes") or {})
    mode_config = (mode_limits.get(mode) or {})

    # If no mode-specific limits configured, allow by default
    if not mode_config:
        return True, None

    # Check max_open limit
    max_open = mode_config.get("max_open")
    if max_open is not None:
        current_count = portfolio.active_counts_by_mode.get(mode, 0)
        if current_count >= max_open:
            reason = RISK_MODE_LIMIT
            assert_reason_known(reason)
            return False, reason

    # Check max_exposure_usd limit
    max_exposure = mode_config.get("max_exposure_usd")
    if max_exposure is not None:
        current_exposure = portfolio.exposure_by_mode.get(mode, 0.0)
        if current_exposure + trade_size >= max_exposure:
            reason = RISK_MODE_LIMIT
            assert_reason_known(reason)
            return False, reason

    return True, None


def _check_exposure_limits(
    *,
    trade: Trade,
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Check per-token exposure limits.

    Args:
        trade: The trade to evaluate
        portfolio: Current portfolio state
        cfg: Strategy configuration dict

    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
    """
    # Get risk limits from config
    risk = (cfg.get("risk") or {})
    limits = (risk.get("limits") or {})

    # Check if per-token exposure limits are enabled
    max_exposure_per_token_pct = limits.get("max_exposure_per_token_pct")
    if max_exposure_per_token_pct is None:
        # Not configured, allow by default
        return True, None

    # Get token mint from trade
    if hasattr(trade, 'mint'):
        mint = trade.mint
    elif isinstance(trade, dict):
        mint = trade.get('mint', '')
    else:
        return True, None

    if not mint:
        return True, None

    # Calculate max exposure in USD
    equity = max(float(portfolio.equity_usd), 0.0)
    max_exposure_usd = equity * (max_exposure_per_token_pct / 100.0)

    # Get current exposure for this token
    current_exposure = float(portfolio.exposure_by_token.get(mint, 0.0))

    # Check if current exposure exceeds the limit
    if current_exposure >= max_exposure_usd:
        reason = RISK_MAX_EXPOSURE
        assert_reason_known(reason)
        return False, reason

    return True, None


def _parse_ts_to_unix(ts_str: str) -> float:
    """Parse datetime string to Unix timestamp.
    
    Handles formats like '2026-01-05 10:00:00.000' -> Unix timestamp.
    """
    if not ts_str:
        return 0.0
    try:
        # Try parsing as Unix timestamp (numeric string)
        return float(ts_str)
    except ValueError:
        pass
    try:
        # Parse datetime string format 'YYYY-MM-DD HH:MM:SS.sss'
        # Convert to Unix timestamp using time.mktime (local time) or parse as UTC
        from datetime import datetime
        dt = datetime.strptime(ts_str.replace(' ', 'T'), '%Y-%m-%dT%H:%M:%S.%f')
        return dt.timestamp()
    except ValueError:
        # Try without milliseconds
        try:
            from datetime import datetime
            dt = datetime.strptime(ts_str.replace(' ', 'T'), '%Y-%m-%dT%H:%M:%S')
            return dt.timestamp()
        except ValueError:
            return 0.0


def should_kill_switch(portfolio: PortfolioStub, cfg: Dict[str, Any]) -> bool:
    risk = (cfg.get("risk") or {})
    limits = (risk.get("limits") or {})
    if not bool(limits.get("kill_switch_on_drawdown", True)):
        return False
    max_dd = limits.get("max_drawdown_total_pct")
    if max_dd is None:
        return False
    return portfolio.drawdown_pct >= float(max_dd)


def apply_risk_limits(
    *,
    trade: Trade,
    signal: Optional[Any],
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Apply P0 risk checks to a trade.

    Args:
        trade: The trade to evaluate
        signal: Optional signal (dict or Signal object, accepted but not used in P0)
        portfolio: Current portfolio state
        cfg: Strategy configuration dict

    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
        - (True, None) if trade is allowed
        - (False, reason) if trade is rejected
    """
    risk = (cfg.get("risk") or {})
    limits = (risk.get("limits") or {})

    # Cooldown: Reject if trade timestamp is before cooldown_until (fail-fast)
    cooldown = (limits.get("cooldown") or {})
    if bool(cooldown.get("enabled", False)):
        # Parse trade.ts to Unix timestamp for comparison
        trade_ts = _parse_ts_to_unix(trade.ts)
        if trade_ts < portfolio.cooldown_until:
            reason = RISK_COOLDOWN
            assert_reason_known(reason)
            return False, reason

    # Wallet Tier Limits: Check tier-specific position limits
    allowed, reason = _check_tier_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not allowed:
        return False, reason

    # Mode Limits: Check mode-specific position limits
    allowed, reason = _check_mode_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not allowed:
        return False, reason

    # Exposure Limits: Check per-token exposure limits
    allowed, reason = _check_exposure_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not allowed:
        return False, reason

    # Kill-Switch: Reject if daily loss exceeds configured threshold
    max_daily_loss_pct = limits.get("max_daily_loss_pct")
    if max_daily_loss_pct is not None:
        # Use peak_equity_usd as proxy for initial_bankroll if not available
        initial_bankroll = getattr(portfolio, "initial_bankroll", portfolio.peak_equity_usd)
        daily_loss_threshold = max_daily_loss_pct * initial_bankroll
        if portfolio.day_pnl_usd <= -daily_loss_threshold:
            reason = RISK_KILL_SWITCH
            assert_reason_known(reason)
            return False, reason

    # Max Open Positions: Reject if too many positions are open
    max_open_positions = limits.get("max_open_positions")
    if max_open_positions is not None:
        if portfolio.open_positions >= max_open_positions:
            reason = RISK_MAX_POSITIONS
            assert_reason_known(reason)
            return False, reason

    # Trade is allowed
    return True, None


def compute_position_size_usd(
    *,
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
    p_model: Optional[float] = None,
    edge_pct: Optional[float] = None,
    estimated_payoff: Optional[float] = None,
    trade_mint: Optional[str] = None,
    risk_regime: float = 0.0,  # PR-F.3: Polymarket regime scalar [-1, 1]
) -> float:
    """Compute position size in USD based on Kelly criterion.

    Args:
        portfolio: Current portfolio state
        cfg: Strategy configuration dict
        p_model: Model probability (0-1)
        edge_pct: Pre-computed edge percentage
        estimated_payoff: Win/loss ratio (b = tp_pct / abs(sl_pct))
        trade_mint: Token mint for exposure limiting

    Returns:
        Position size in USD
    """
    risk = (cfg.get("risk") or {})
    sizing = (risk.get("sizing") or {})
    limits = (risk.get("limits") or {})
    method = str(sizing.get("method", "fixed_pct"))

    min_pos = float(sizing.get("min_pos_pct", 0.5))
    max_pos = float(sizing.get("max_pos_pct", 2.0))
    equity = max(float(portfolio.equity_usd), 0.0)

    pos_pct = float(sizing.get("fixed_pct_of_bankroll", 1.0))

    if method == "fractional_kelly":
        kf = float(sizing.get("kelly_fraction", 0.25))

        # Calculate Kelly fraction using payoff ratio
        if estimated_payoff is not None and p_model is not None and estimated_payoff > 0:
            # Full Kelly: f* = (p * (b + 1) - 1) / b
            # where b = estimated_payoff (win/loss ratio)
            b = float(estimated_payoff)
            p = float(p_model)
            f_star = (p * (b + 1) - 1) / b  # Returns fraction (e.g., 0.475 = 47.5%)
            # Apply fractional Kelly and convert to percentage
            kelly_pct = (kf * max(0.0, f_star)) * 100.0
            pos_pct = kelly_pct
        elif edge_pct is None:
            # Fall back to proxy edge calculation
            proxy = (sizing.get("proxy_edge") or {})
            if bool(proxy.get("enabled", True)) and p_model is not None:
                baseline = float(proxy.get("p_model_baseline", 0.55))
                per = float(proxy.get("edge_per_0_01_p", 1.5))
                dp = max(0.0, float(p_model) - baseline)
                edge_pct = (dp / 0.01) * per
            else:
                edge_pct = 0.0
            pos_pct = kf * max(0.0, float(edge_pct))
        else:
            pos_pct = kf * max(0.0, float(edge_pct))

    # Apply min/max position size clamps
    pos_pct = max(min_pos, min(max_pos, pos_pct))

    # Calculate raw position size
    position_size = equity * (pos_pct / 100.0)

    # Apply per-token exposure limits if configured
    max_exposure_per_token_pct = limits.get("max_exposure_per_token_pct")
    if max_exposure_per_token_pct is not None and trade_mint:
        max_exposure_usd = equity * (max_exposure_per_token_pct / 100.0)
        current_exposure = float(portfolio.exposure_by_token.get(trade_mint, 0.0))
        remaining_exposure = max_exposure_usd - current_exposure
        position_size = min(position_size, remaining_exposure)

    # PR-F.3: Apply Polymarket regime adjustment
    adjustment_cfg = cfg.get("adjustments", {})
    if risk_regime != 0.0:
        position_size = adjust_position_size(
            base_size=position_size,
            regime=risk_regime,
            cfg=adjustment_cfg,
        )

    return position_size


# PR-E.2.1: Aggressive Mode Safety Gates

@dataclass
class AggressiveSafetyContext:
    """Context for aggressive mode safety filter evaluation.

    Attributes:
        wallet_winrate_30d: Wallet 30-day winrate (0-1).
        wallet_roi_30d_pct: Wallet 30-day ROI percentage.
        token_liquidity_usd: Token liquidity in USD.
        token_top10_holders_pct: Percentage of supply held by top 10 holders.
        daily_loss_pct: Current daily loss percentage (negative value, e.g., -0.03 for -3%).
        aggr_trades_today: Number of aggressive trades executed today.
        aggr_open_positions: Number of open aggressive positions.
    """
    wallet_winrate_30d: Optional[float] = None
    wallet_roi_30d_pct: Optional[float] = None
    token_liquidity_usd: Optional[float] = None
    token_top10_holders_pct: Optional[float] = None
    daily_loss_pct: float = 0.0
    aggr_trades_today: int = 0
    aggr_open_positions: int = 0


def passes_safety_filters(
    ctx: AggressiveSafetyContext,
    cfg: Dict[str, Any],
) -> bool:
    """Check if aggressive mode is allowed based on safety filters.

    PR-E.2.1: Fail-safe default - if any data is missing, returns False.
    Hierarchy: Global Risk State > Token Safety > Wallet Quality.

    Args:
        ctx: Safety context with wallet, token, and risk state.
        cfg: Strategy config dict with aggressive safety filter thresholds.

    Returns:
        True if aggressive mode is allowed, False otherwise.
    """
    # Get aggressive safety filter configuration
    aggressive = (cfg.get("aggressive") or {})
    safety = (aggressive.get("safety_filters") or {})

    # Get limits configuration
    limits = (safety.get("limits") or {})

    # 1. Check Global Risk State (highest priority)
    # If daily loss exceeds threshold, block aggressive mode
    risk_state_cfg = (safety.get("risk_state") or {})
    max_daily_loss = risk_state_cfg.get("disable_if_daily_loss_ge", 0.05)
    if ctx.daily_loss_pct <= -max_daily_loss:
        return False

    # 2. Check Aggressive Limits
    max_aggr_trades = limits.get("max_aggr_trades_per_day", 10)
    if ctx.aggr_trades_today >= max_aggr_trades:
        return False

    max_aggr_open = limits.get("max_aggr_open_positions", 3)
    if ctx.aggr_open_positions >= max_aggr_open:
        return False

    # 3. Check Wallet Quality (fail-safe: missing data = False)
    wallet_cfg = (safety.get("wallet") or {})
    min_winrate = wallet_cfg.get("min_winrate_30d", 0.60)
    min_roi = wallet_cfg.get("min_roi_30d_pct", 25.0) / 100.0  # Convert to decimal

    # Fail-safe: if wallet data is missing, return False
    if ctx.wallet_winrate_30d is None:
        return False
    if ctx.wallet_roi_30d_pct is None:
        return False

    if ctx.wallet_winrate_30d < min_winrate:
        return False
    if ctx.wallet_roi_30d_pct < min_roi:
        return False

    # 4. Check Token Safety (fail-safe: missing data = False)
    token_cfg = (safety.get("token") or {})
    min_liquidity = token_cfg.get("min_liquidity_usd", 20000)
    max_top10_holders = token_cfg.get("max_top10_holders_pct", 0.85)

    # Fail-safe: if token data is missing, return False
    if ctx.token_liquidity_usd is None:
        return False
    if ctx.token_top10_holders_pct is None:
        return False

    if ctx.token_liquidity_usd < min_liquidity:
        return False
    if ctx.token_top10_holders_pct > max_top10_holders:
        return False

    # All checks passed
    return True


def allow_aggressive_trade(
    ctx: AggressiveSafetyContext,
    cfg: Dict[str, Any],
) -> Tuple[bool, str]:
    """Determine if an aggressive trade is allowed.

    Combines safety filters with a human-readable reason.

    Args:
        ctx: Safety context with wallet, token, and risk state.
        cfg: Strategy config dict with aggressive safety filter thresholds.

    Returns:
        Tuple of (allowed: bool, reason: str).
    """
    # Check if aggressive mode is enabled in config
    aggressive = (cfg.get("aggressive") or {})
    if not aggressive.get("enabled", False):
        return False, "Aggressive mode disabled in config"

    # Run safety filters
    if not passes_safety_filters(ctx, cfg):
        # Determine which check failed for the reason
        safety = (aggressive.get("safety_filters") or {})
        limits = (safety.get("limits") or {})
        risk_state_cfg = (safety.get("risk_state") or {})
        wallet_cfg = (safety.get("wallet") or {})
        token_cfg = (safety.get("token") or {})

        # Check each condition in hierarchy order
        max_daily_loss = risk_state_cfg.get("disable_if_daily_loss_ge", 0.05)
        if ctx.daily_loss_pct <= -max_daily_loss:
            return False, f"Daily loss {ctx.daily_loss_pct*100:.1f}% >= threshold {max_daily_loss*100:.1f}%"

        max_aggr_trades = limits.get("max_aggr_trades_per_day", 10)
        if ctx.aggr_trades_today >= max_aggr_trades:
            return False, f"Aggressive trades today ({ctx.aggr_trades_today}) >= limit ({max_aggr_trades})"

        max_aggr_open = limits.get("max_aggr_open_positions", 3)
        if ctx.aggr_open_positions >= max_aggr_open:
            return False, f"Open aggressive positions ({ctx.aggr_open_positions}) >= limit ({max_aggr_open})"

        min_winrate = wallet_cfg.get("min_winrate_30d", 0.60)
        if ctx.wallet_winrate_30d is not None and ctx.wallet_winrate_30d < min_winrate:
            return False, f"Wallet winrate {ctx.wallet_winrate_30d*100:.1f}% < required {min_winrate*100:.1f}%"

        min_roi = wallet_cfg.get("min_roi_30d_pct", 25.0) / 100.0
        if ctx.wallet_roi_30d_pct is not None and ctx.wallet_roi_30d_pct < min_roi:
            return False, f"Wallet ROI {ctx.wallet_roi_30d_pct*100:.1f}% < required {min_roi*100:.1f}%"

        min_liquidity = token_cfg.get("min_liquidity_usd", 20000)
        if ctx.token_liquidity_usd is not None and ctx.token_liquidity_usd < min_liquidity:
            return False, f"Token liquidity ${ctx.token_liquidity_usd:,.0f} < required ${min_liquidity:,.0f}"

        max_top10 = token_cfg.get("max_top10_holders_pct", 0.85)
        if ctx.token_top10_holders_pct is not None and ctx.token_top10_holders_pct > max_top10:
            return False, f"Top 10 holders {ctx.token_top10_holders_pct*100:.1f}% > limit {max_top10*100:.1f}%"

        # Fallback for missing data
        return False, "Safety filter failed (unknown reason)"

    return True, "Aggressive mode allowed"
