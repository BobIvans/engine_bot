"""
strategy/execution_math.py - Slippage Estimation Math

Pure mathematical functions for estimating execution costs:
- Slippage based on trade size vs pool liquidity
- Price impact calculations

HARD RULES:
1. Purity: Only math, no RPC calls
2. Safety: Division by zero protection, returns MAX_SLIPPAGE_BPS
3. Clamping: Results bounded to reasonable limits
"""

import math
from typing import Optional


# Constants
MAX_SLIPPAGE_BPS = 10000  # 100% slippage (complete failure)
BPS_SCALE = 10000  # 1 bps = 0.01%


def calculate_linear_impact_bps(
    size_usd: float,
    liquidity_usd: float,
    impact_scalar: float = 0.5
) -> float:
    """
    Calculate price impact in basis points using linear approximation.

    Formula: bps = (size_usd / liquidity_usd) * 10_000 * scalar

    This is a linear approximation of the x*y=k curve for small trades.
    For larger trades (size approaching liquidity), the curve becomes
    non-linear and impact grows faster.

    Args:
        size_usd: Trade size in USD
        liquidity_usd: Pool liquidity in USD
        impact_scalar: Coefficient for impact adjustment (default 0.5)
                      Lower values = less impact (deeper pools)
                      Higher values = more impact (shallow pools)

    Returns:
        Slippage in basis points (0 to MAX_SLIPPAGE_BPS)
        - 0 bps = no slippage
        - 10000 bps = 100% slippage (worst case)
    """
    # Safety checks
    if size_usd <= 0:
        return 0.0

    if liquidity_usd <= 0:
        return MAX_SLIPPAGE_BPS

    if math.isnan(size_usd) or math.isnan(liquidity_usd):
        return MAX_SLIPPAGE_BPS

    if math.isnan(impact_scalar) or impact_scalar <= 0:
        impact_scalar = 0.5  # Default safe value

    # Linear impact formula
    size_ratio = size_usd / liquidity_usd
    raw_bps = size_ratio * BPS_SCALE * impact_scalar

    # If size exceeds liquidity, apply non-linear penalty
    if size_ratio >= 1.0:
        # When size >= liquidity, use maximum slippage
        # This simulates attempting to drain the pool
        raw_bps = MAX_SLIPPAGE_BPS
    else:
        # Clamp to reasonable bounds
        raw_bps = max(0.0, min(MAX_SLIPPAGE_BPS, raw_bps))

    return raw_bps


def estimate_slippage_with_spread(
    size_usd: float,
    liquidity_usd: float,
    base_spread_bps: float = 0,
    impact_scalar: float = 0.5
) -> float:
    """
    Estimate total cost including both slippage and spread.

    Args:
        size_usd: Trade size in USD
        liquidity_usd: Pool liquidity in USD
        base_spread_bps: Base spread in bps (from order book)
        impact_scalar: Impact coefficient

    Returns:
        Total cost in bps (slippage + spread)
    """
    slippage_bps = calculate_linear_impact_bps(
        size_usd=size_usd,
        liquidity_usd=liquidity_usd,
        impact_scalar=impact_scalar
    )

    total_bps = slippage_bps + base_spread_bps

    # Clamp to max
    return min(total_bps, MAX_SLIPPAGE_BPS)


def calculate_slippage_for_position(
    position_size_usd: float,
    liquidity_usd: float,
    impact_scalar: float = 0.5,
    max_slippage_bps: float = 1000  # 10% max acceptable
) -> tuple:
    """
    Calculate slippage and determine if trade is acceptable.

    Args:
        position_size_usd: Position size in USD
        liquidity_usd: Pool liquidity in USD
        impact_scalar: Impact coefficient
        max_slippage_bps: Maximum acceptable slippage

    Returns:
        Tuple of (slippage_bps: float, is_acceptable: bool)
    """
    slippage_bps = calculate_linear_impact_bps(
        size_usd=position_size_usd,
        liquidity_usd=liquidity_usd,
        impact_scalar=impact_scalar
    )

    is_acceptable = slippage_bps <= max_slippage_bps

    return slippage_bps, is_acceptable


# Convenience function for quick calculations
def quick_slippage(
    size_usd: float,
    liquidity_usd: float
) -> float:
    """
    Quick slippage estimate with default parameters.

    Args:
        size_usd: Trade size in USD
        liquidity_usd: Pool liquidity in USD

    Returns:
        Slippage in basis points
    """
    return calculate_linear_impact_bps(
        size_usd=size_usd,
        liquidity_usd=liquidity_usd,
        impact_scalar=0.5  # Default scalar
    )


if __name__ == "__main__":
    # Self-test
    print("Slippage Math Self-Test")
    print("=" * 50)

    # Case 1: $100 trade, $1M liquidity
    # Expected: (100 / 1_000_000) * 10_000 * 0.5 = 0.5 bps
    slippage1 = calculate_linear_impact_bps(100, 1_000_000, 0.5)
    print(f"$100 trade, $1M liquidity: {slippage1:.2f} bps (expected ~0.5)")

    # Case 2: $10k trade, $50k liquidity
    # Expected: (10_000 / 50_000) * 10_000 * 0.5 = 1000 bps
    slippage2 = calculate_linear_impact_bps(10_000, 50_000, 0.5)
    print(f"$10k trade, $50k liquidity: {slippage2:.2f} bps (expected ~1000)")

    # Case 3: Zero liquidity
    slippage3 = calculate_linear_impact_bps(100, 0, 0.5)
    print(f"Zero liquidity: {slippage3} bps (expected {MAX_SLIPPAGE_BPS})")

    # Case 4: Negative liquidity
    slippage4 = calculate_linear_impact_bps(100, -100, 0.5)
    print(f"Negative liquidity: {slippage4} bps (expected {MAX_SLIPPAGE_BPS})")

    # Case 5: Size >= liquidity
    slippage5 = calculate_linear_impact_bps(100_000, 50_000, 0.5)
    print(f"Size >= liquidity: {slippage5} bps (expected {MAX_SLIPPAGE_BPS})")

    # Case 6: NaN handling
    slippage6 = calculate_linear_impact_bps(float('nan'), 100_000, 0.5)
    print(f"NaN size: {slippage6} bps (expected {MAX_SLIPPAGE_BPS})")
