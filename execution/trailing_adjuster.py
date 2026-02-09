"""execution/trailing_adjuster.py

PR-Z.3 Trailing Stop Dynamic Adjustment.

Adaptive trailing stop distance based on realized volatility and volume profile.
Thread-safe, deterministic, works in both simulator and live execution.
"""

import sys
from typing import Literal, Optional

from config.runtime_schema import RuntimeConfig
from execution.market_features import MarketContext


class TrailingAdjuster:
    """Computes adaptive trailing stop distance based on market conditions.
    
    Adaptation rules:
    - High volatility (rv_5m > threshold): expand distance (protection from noise)
    - Low volatility (rv_5m < threshold): contract distance (faster profit capture)
    - Confirming volume (direction matches position): contract distance
    - Contrarian volume: expand distance slightly
    
    Safety:
    - Hard cap at trailing_max_distance_bps
    - Soft floor at 50% of base distance
    - Outlier rejection for extreme volatility (>50%)
    """
    
    def __init__(self, config: RuntimeConfig):
        """Initialize with runtime configuration.
        
        Args:
            config: RuntimeConfig with dynamic trailing parameters.
        """
        self._config = config
        self._log_level = 0  # 0=off, 1=basic, 2=verbose
    
    def _log_adjustment(
        self,
        base: int,
        adjusted: int,
        rv_5m: float,
        volume_multiplier: float
    ) -> None:
        """Log adjustment to stderr for smoke test verification."""
        if self._log_level >= 1:
            vol_str = f"volume={volume_multiplier:+.1f}×" if volume_multiplier != 1.0 else "volume=neutral"
            msg = f"[trailing] Adjusted: {base} → {adjusted} bps (RV={rv_5m:.2f}, {vol_str})"
            print(msg, file=sys.stderr)
    
    def compute_distance_bps(
        self,
        base_distance_bps: int,
        market_ctx: MarketContext,
        position_side: Literal["LONG", "SHORT"],
        unrealized_pnl_pct: float,
        log: bool = False
    ) -> int:
        """Compute adaptive trailing stop distance in basis points.
        
        Args:
            base_distance_bps: Base trailing distance without adaptation.
            market_ctx: Current market context with volatility/volume features.
            position_side: Position direction (LONG or SHORT).
            unrealized_pnl_pct: Current unrealized P&L as percentage.
            log: Whether to log adjustment details to stderr.
            
        Returns:
            Adaptive trailing distance in basis points.
        """
        # Validate market context to reject outliers
        if not market_ctx.validate():
            if log:
                print(f"[trailing] WARNING: Invalid market context, using base distance", file=sys.stderr)
            return base_distance_bps
        
        # Enable verbose logging if requested
        self._log_level = 2 if log else 0
        
        distance = float(base_distance_bps)
        config = self._config
        volume_multiplier = 1.0  # Track for logging
        
        # === VOLATILITY ADAPTATION ===
        if market_ctx.rv_5m > config.trailing_rv_threshold_high:
            # High volatility: expand distance for noise protection
            distance *= config.trailing_volatility_multiplier
        elif market_ctx.rv_5m < config.trailing_rv_threshold_low:
            # Low volatility: contract distance for faster profit capture
            distance *= max(0.7, config.trailing_volatility_multiplier * 0.8)
        
        # === VOLUME ADAPTATION ===
        # Only apply volume adaptation when there's meaningful unrealized profit
        # This prevents premature tightening of stops
        if unrealized_pnl_pct > 0.5:  # >0.5% profit threshold
            volume_delta = market_ctx.volume_delta_1m
            threshold = config.trailing_volume_confirm_threshold
            
            if position_side == "LONG" and volume_delta > threshold:
                # Confirming volume (buys for long): contract stop
                distance *= config.trailing_volume_multiplier
                volume_multiplier = config.trailing_volume_multiplier
            elif position_side == "SHORT" and volume_delta < -threshold:
                # Confirming volume (sells for short): contract stop
                distance *= config.trailing_volume_multiplier
                volume_multiplier = config.trailing_volume_multiplier
            elif abs(volume_delta) > threshold * 1.5:
                # Strong contrarian volume: expand slightly
                distance *= 1.2
                volume_multiplier = 1.2
        
        # === SAFETY CLAMPS ===
        # Hard cap: never exceed maximum to protect unrealized profit
        distance = min(distance, config.trailing_max_distance_bps)
        
        # Soft floor: never go below 50% of base (too tight is dangerous)
        min_floor = base_distance_bps * 0.5
        distance = max(distance, min_floor)
        
        adjusted = int(round(distance))
        
        # Log adjustment if requested (for smoke test)
        if log:
            self._log_adjustment(
                base=base_distance_bps,
                adjusted=adjusted,
                rv_5m=market_ctx.rv_5m,
                volume_multiplier=volume_multiplier
            )
        
        return adjusted


def create_trailing_adjuster(config: RuntimeConfig) -> TrailingAdjuster:
    """Factory function to create TrailingAdjuster from config.
    
    Args:
        config: RuntimeConfig with dynamic trailing parameters.
        
    Returns:
        Configured TrailingAdjuster instance.
    """
    return TrailingAdjuster(config)
