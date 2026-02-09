"""
ingestion/dex/raydium/math.py

Raydium AMM Math - Pure functions for swap calculations.

PR-U.1
"""
from dataclasses import dataclass
from typing import Tuple


# Default Raydium fee: 0.25% = 25 bps / 10000
DEFAULT_FEE_BPS = 25


@dataclass
class SwapResult:
    """Result of a swap calculation."""
    amount_out: int          # Amount out (atomic units)
    price_impact_bps: int   # Price impact in basis points
    effective_price: float   # Effective price (out/in)
    mid_price: float        # Mid price before trade
    
    def to_dict(self) -> dict:
        return {
            "amount_out": self.amount_out,
            "price_impact_bps": self.price_impact_bps,
            "effective_price": self.effective_price,
            "mid_price": self.mid_price,
        }


def get_amount_out(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee_bps: int = DEFAULT_FEE_BPS,
) -> int:
    """
    Calculate amount out for a swap using xy=k formula with fees.
    
    Formula:
    amount_in_with_fee = amount_in * (10000 - fee_bps)
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 10000 + amount_in_with_fee
    amount_out = numerator / denominator
    
    Args:
        amount_in: Amount in (atomic units)
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee_bps: Fee in basis points (default 25 for 0.25%)
        
    Returns:
        Amount out (atomic units)
    """
    if amount_in <= 0:
        raise ValueError("amount_in must be positive")
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("reserves must be positive")
    
    # Calculate amount after fee
    fee_numerator = 10000 - fee_bps
    amount_in_with_fee = amount_in * fee_numerator
    
    # Calculate numerator and denominator
    numerator = amount_in_with_fee * reserve_out
    denominator = (reserve_in * 10000) + amount_in_with_fee
    
    # Calculate amount out
    amount_out = numerator // denominator
    
    return amount_out


def get_amount_in(
    amount_out: int,
    reserve_in: int,
    reserve_out: int,
    fee_bps: int = DEFAULT_FEE_BPS,
) -> int:
    """
    Calculate amount in for a desired amount out.
    
    Reverse of get_amount_out.
    
    Args:
        amount_out: Desired amount out (atomic units)
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee_bps: Fee in basis points
        
    Returns:
        Amount in (atomic units)
    """
    if amount_out <= 0:
        raise ValueError("amount_out must be positive")
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("reserves must be positive")
    if amount_out >= reserve_out:
        raise ValueError("amount_out >= reserve_out (would drain pool)")
    
    # Reverse formula
    numerator = amount_out * reserve_in * 10000
    denominator = (reserve_out - amount_out) * (10000 - fee_bps)
    
    amount_in = (numerator // denominator) + 1  # Add 1 for rounding
    
    return amount_in


def get_price_impact_bps(
    amount_in: int,
    amount_out: int,
    reserve_in: int,
    reserve_out: int,
) -> int:
    """
    Calculate price impact in basis points.
    
    Price impact = (effective_price - mid_price) / mid_price * 10000
    
    Where:
    - effective_price = amount_in / amount_out
    - mid_price = sqrt(reserve_in / reserve_out) / sqrt(reserve_in / reserve_out) = reserve_in / reserve_out
    - Actually mid_price = reserve_out / reserve_in
    
    Args:
        amount_in: Amount in
        amount_out: Amount out
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        
    Returns:
        Price impact in basis points (1% = 100 bps)
    """
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("reserves must be positive")
    
    # Mid price (before trade): how much output you get for 1 unit input
    # mid_price = amount_out_before / amount_in_before
    # But reserves give us: 1 unit input = reserve_out / reserve_in units output
    # So mid_price = reserve_out / reserve_in
    
    # Effective price (after trade): how much output you actually get for 1 unit input
    # effective_price = amount_out / amount_in
    
    # For the trade:
    # If we trade amount_in, we get amount_out
    # effective_price = amount_out / amount_in
    
    # Mid price per unit input
    mid_price_per_unit = reserve_out / reserve_in
    
    # Effective price per unit input
    effective_price_per_unit = amount_out / amount_in
    
    # Price impact
    impact = (effective_price_per_unit - mid_price_per_unit) / mid_price_per_unit
    
    # Convert to basis points
    impact_bps = int(impact * 10000)
    
    return impact_bps


def calculate_swap(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee_bps: int = DEFAULT_FEE_BPS,
) -> SwapResult:
    """
    Calculate full swap result including price impact.
    
    Args:
        amount_in: Amount in (atomic units)
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee_bps: Fee in basis points
        
    Returns:
        SwapResult with amount_out and price_impact_bps
    """
    # Calculate amount out
    amount_out = get_amount_out(amount_in, reserve_in, reserve_out, fee_bps)
    
    # Calculate price impact
    impact_bps = get_price_impact_bps(amount_in, amount_out, reserve_in, reserve_out)
    
    # Calculate effective price
    effective_price = amount_out / amount_in
    
    # Mid price
    mid_price = reserve_out / reserve_in
    
    return SwapResult(
        amount_out=amount_out,
        price_impact_bps=impact_bps,
        effective_price=effective_price,
        mid_price=mid_price,
    )


def get_lp_token_value(
    lp_supply: int,
    reserve_a: int,
    reserve_b: int,
    lp_amount: int,
) -> Tuple[int, int]:
    """
    Calculate value of LP tokens in terms of underlying tokens.
    
    Args:
        lp_supply: Total LP token supply
        reserve_a: Reserve of token A
        reserve_b: Reserve of token B
        lp_amount: Amount of LP tokens to value
        
    Returns:
        Tuple of (amount_a, amount_b)
    """
    if lp_supply <= 0:
        raise ValueError("lp_supply must be positive")
    
    share = lp_amount / lp_supply
    
    amount_a = int(reserve_a * share)
    amount_b = int(reserve_b * share)
    
    return amount_a, amount_b


def get_y_per_x(
    reserve_x: int,
    reserve_y: int,
    amount_x: int,
    fee_bps: int = DEFAULT_FEE_BPS,
) -> int:
    """
    Calculate how much Y you get for X tokens.
    
    Args:
        reserve_x: Reserve of X
        reserve_y: Reserve of Y
        amount_x: Amount of X to swap
        fee_bps: Fee in basis points
        
    Returns:
        Amount of Y
    """
    return get_amount_out(amount_x, reserve_x, reserve_y, fee_bps)


def get_x_per_y(
    reserve_x: int,
    reserve_y: int,
    amount_y: int,
    fee_bps: int = DEFAULT_FEE_BPS,
) -> int:
    """
    Calculate how much X you get for Y tokens.
    
    Args:
        reserve_x: Reserve of X
        reserve_y: Reserve of Y
        amount_y: Amount of Y to swap
        fee_bps: Fee in basis points
        
    Returns:
        Amount of X
    """
    return get_amount_out(amount_y, reserve_y, reserve_x, fee_bps)


def calculate_k_constant(
    reserve_a: int,
    reserve_b: int,
) -> int:
    """
    Calculate the k constant (xy=k).
    
    Args:
        reserve_a: Reserve of token A
        reserve_b: Reserve of token B
        
    Returns:
        k constant
    """
    return reserve_a * reserve_b


def check_k_invariant(
    reserve_a: int,
    reserve_b: int,
    new_reserve_a: int,
    new_reserve_b: int,
    tolerance: int = 1,
) -> bool:
    """
    Check if k invariant holds (with tolerance for rounding).
    
    Args:
        reserve_a: Original reserve A
        reserve_b: Original reserve B
        new_reserve_a: New reserve A
        new_reserve_b: New reserve B
        tolerance: Tolerance for rounding errors
        
    Returns:
        True if invariant holds
    """
    k_before = reserve_a * reserve_b
    k_after = new_reserve_a * new_reserve_b
    
    # Allow some tolerance for rounding
    return abs(k_before - k_after) <= tolerance * 1000
