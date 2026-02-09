"""strategy/dynamic_adjustment.py

PR-E.3 Dynamic TTL & Slippage Model.

Pure functions for:
- Dynamic TTL calculation based on volatility
- Advanced slippage estimation based on liquidity, size, and volatility

Design goals:
- Pure logic (stateless)
- Deterministic output
- No stdout pollution
"""

from typing import Any, Dict


def calculate_dynamic_ttl(
    base_ttl: int,
    vol_30s: float,
    cfg: Dict[str, Any]
) -> int:
    """Calculate dynamic Time-To-Live based on market volatility.

    Higher volatility = shorter TTL (adaptive to fast-moving markets).

    Formula: ttl = base_ttl / (1 + factor * vol_30s)

    Args:
        base_ttl: Base TTL in milliseconds.
        vol_30s: 30-second volatility metric (e.g., price std dev / price).
        cfg: Dynamic execution config dict.

    Returns:
        Effective TTL in milliseconds (rounded to int).
    """
    # Extract config
    dynamic_cfg = cfg.get("dynamic_execution", {})
    if not dynamic_cfg.get("enabled", False):
        return base_ttl

    factor = dynamic_cfg.get("ttl_vol_factor", 10.0)  # Default: 10x vol sensitivity
    min_ttl = dynamic_cfg.get("min_ttl_ms", 500)  # Minimum 500ms

    # Calculate dynamic TTL
    denominator = 1.0 + factor * vol_30s
    dynamic_ttl = base_ttl / denominator

    # Apply minimum TTL floor
    return int(max(dynamic_ttl, min_ttl))


def calculate_slippage_bps(
    base_bps: float,
    size_usd: float,
    liq_usd: float,
    vol_30s: float,
    cfg: Dict[str, Any]
) -> float:
    """Calculate dynamic slippage in basis points.

    Slippage increases with:
    - Larger trade size relative to liquidity
    - Higher volatility

    Formula: impact = base_bps + (slope * size / liq) * (1 + vol_mult * vol_30s)

    Args:
        base_bps: Base slippage in basis points.
        size_usd: Trade size in USD.
        liq_usd: Available liquidity in USD.
        vol_30s: 30-second volatility metric.
        cfg: Dynamic execution config dict.

    Returns:
        Slippage in basis points.
    """
    # Extract config
    dynamic_cfg = cfg.get("dynamic_execution", {})
    if not dynamic_cfg.get("enabled", False):
        return base_bps

    slope = dynamic_cfg.get("slippage_slope", 0.01)  # Size/Liq impact coefficient
    vol_mult = dynamic_cfg.get("slippage_vol_mult", 5.0)  # Volatility multiplier

    # Calculate impact from size/liquidity ratio
    size_liq_ratio = size_usd / liq_usd if liq_usd > 0 else 0.0
    size_impact = slope * size_liq_ratio

    # Calculate volatility multiplier
    vol_multiplier = 1.0 + vol_mult * vol_30s

    # Total slippage = base + (size impact * vol multiplier)
    total_bps = base_bps + (size_impact * vol_multiplier)

    return total_bps


def extract_volatility(
    trade_extra: Dict[str, Any],
    snapshot_extra: Dict[str, Any]
) -> float:
    """Extract volatility metric from trade or snapshot extra data.

    Args:
        trade_extra: Trade.extra dict (may contain vol_30s).
        snapshot_extra: TokenSnapshot.extra dict (may contain vol_30s).

    Returns:
        vol_30s value, defaults to 0.0 if not found.
    """
    # Prefer trade extra, fallback to snapshot
    if "vol_30s" in trade_extra:
        return float(trade_extra["vol_30s"])
    if "vol_30s" in snapshot_extra:
        return float(snapshot_extra["vol_30s"])
    return 0.0
