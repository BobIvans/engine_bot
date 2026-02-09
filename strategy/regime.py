"""Polymarket Regime Overlay.

Pure logic for calculating global market regime based on Polymarket data.
No API calls, no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RegimeResult:
    """Result of market regime evaluation.

    Attributes:
        score: Bullish score normalized to -1.0..+1.0.
        risk_off: True if market regime is risk-off (conservative).
        reason: Human-readable reason for the regime decision.
    """
    score: float
    risk_off: bool
    reason: str


def calculate_regime(market_data: Dict[str, Any], params: Dict[str, Any]) -> RegimeResult:
    """Calculate market regime from Polymarket market data.

    This is a pure function - it only accepts values and returns a result.
    No API calls or side effects.

    Args:
        market_data: Dict with market probabilities from Polymarket API.
            Expected fields:
            - p_yes: Probability of YES outcome (0.0 to 1.0)
            - p_no: Probability of NO outcome (0.0 to 1.0)
            - p_crash: Optional probability of crash scenario
        params: Configuration dictionary with regime thresholds.
            Expected fields:
            - bullish_threshold: Minimum P_yes for RISK_ON (default: 0.55)
            - crash_threshold: Maximum P_crash for RISK_ON (default: 0.3)

    Returns:
        RegimeResult with score, risk_off, and reason.
    """
    # Extract config values with defaults
    bullish_threshold = float(params.get("bullish_threshold", 0.55))
    crash_threshold = float(params.get("crash_threshold", 0.3))

    # Extract probabilities from market data
    p_yes = market_data.get("p_yes")
    p_no = market_data.get("p_no")
    p_crash = market_data.get("p_crash", 0.0)

    # Rule 1: Default Safety - missing data = Risk-Off
    if p_yes is None or p_no is None:
        return RegimeResult(
            score=0.0,
            risk_off=True,
            reason="MISSING_DATA",
        )

    # Calculate bullish score: (P_bullish - 0.5) * 2 -> normalizes to -1..1
    # P_bullish is represented as P_yes (probability of YES outcome)
    bullish_score = (p_yes - 0.5) * 2

    # Rule 2: Check Crash Risk
    if p_crash > crash_threshold:
        return RegimeResult(
            score=bullish_score,
            risk_off=True,
            reason="HIGH_CRASH_RISK",
        )

    # Rule 3: Check Bullish Threshold
    if p_yes < bullish_threshold:
        return RegimeResult(
            score=bullish_score,
            risk_off=True,
            reason="BEARISH_SENTIMENT",
        )

    # Rule 4: All checks passed - Risk-On
    return RegimeResult(
        score=bullish_score,
        risk_off=False,
        reason="OK",
    )


def adjust_position_size(
    base_size: float,
    regime: float,
    cfg: Dict[str, Any],
) -> float:
    """Adjust position size based on regime score.

    Args:
        base_size: Initial position size in USD.
        regime: Regime score (-1.0 to 1.0).
        cfg: Adjustment configuration.

    Returns:
        Adjusted position size.
    """
    # Simple linear adjustment: size * (1 + regime * scalar)
    scalar = float(cfg.get("regime_scalar", 0.5))
    multiplier = 1.0 + (regime * scalar)
    
    # Clamp multiplier to safe bounds (e.g. 0.0 to 2.0)
    multiplier = max(0.0, min(multiplier, 2.0))
    
    return base_size * multiplier


def load_regime_config(config_path: str) -> Dict[str, Any]:
    """Load regime configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file.

    Returns:
        Configuration dictionary.
    """
    import yaml

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# Example usage (for testing)
if __name__ == "__main__":
    pass
