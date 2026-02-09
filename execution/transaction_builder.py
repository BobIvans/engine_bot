"""execution/transaction_builder.py

Pure logic for building transaction instructions.
Handles partial exits, split orders, and SL updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Dust threshold - trades smaller than this are considered closed
DUST_THRESHOLD_TOKENS = 1.0


@dataclass(frozen=True)
class SwapInstruction:
    """Abstract swap instruction (not network-specific).

    Attributes:
        amount_in_u64: Amount of tokens to sell (integer for precision).
        min_amount_out_u64: Minimum expected output (slippage protection).
        mint: Token mint address.
    """
    amount_in_u64: int
    min_amount_out_u64: int
    mint: str


@dataclass(frozen=True)
class UpdateSLInstruction:
    """Instruction to update stop-loss parameters.

    Attributes:
        new_trail_stop_pct: New trailing stop percentage.
        new_trail_activation_pct: New activation threshold.
    """
    new_trail_stop_pct: float
    new_trail_activation_pct: float


def calculate_swap_amount(
    current_balance_u64: int,
    size_pct: float,
) -> int:
    """Calculate token amount to sell for a partial exit.

    Uses integer arithmetic where possible to avoid floating-point drift.

    Args:
        current_balance_u64: Current token balance as integer.
        size_pct: Percentage of balance to sell (0.0 to 1.0).

    Returns:
        Amount of tokens to sell as integer.

    Raises:
        ValueError: If size_pct is not in (0.0, 1.0] or current_balance is negative.
    """
    if not 0.0 < size_pct <= 1.0:
        raise ValueError(f"size_pct must be 0.0 < size_pct <= 1.0, got {size_pct}")
    if current_balance_u64 < 0:
        raise ValueError(f"current_balance_u64 cannot be negative, got {current_balance_u64}")

    # Use integer arithmetic: floor(current_balance * size_pct)
    amount = int(current_balance_u64 * size_pct)

    # Ensure at least 1 token if size_pct > 0
    if amount < 1:
        amount = 1

    # Don't exceed available balance
    if amount > current_balance_u64:
        amount = current_balance_u64

    return amount


def calculate_min_output(
    amount_in: int,
    current_price: float,
    slippage_bps: int = 100,  # Default 1% slippage
) -> int:
    """Calculate minimum expected output with slippage protection.

    Args:
        amount_in: Amount of tokens to sell.
        current_price: Current market price in USD.
        slippage_bps: Slippage in basis points (default 100 = 1%).

    Returns:
        Minimum USD value expected from the swap.
    """
    # value = amount * price * (1 - slippage)
    slippage_factor = 1.0 - (slippage_bps / 10_000.0)
    min_value = amount_in * current_price * slippage_factor
    return int(min_value)


def build_swap_instruction(
    current_balance_u64: int,
    size_pct: float,
    mint: str,
    current_price: float,
    slippage_bps: int = 100,
) -> SwapInstruction:
    """Build a complete swap instruction for a partial exit.

    Args:
        current_balance_u64: Current token balance.
        size_pct: Percentage of balance to exit.
        mint: Token mint address.
        current_price: Current market price.
        slippage_bps: Slippage tolerance in bps.

    Returns:
        SwapInstruction ready for execution.
    """
    amount = calculate_swap_amount(current_balance_u64, size_pct)
    min_output = calculate_min_output(amount, current_price, slippage_bps)

    return SwapInstruction(
        amount_in_u64=amount,
        min_amount_out_u64=min_output,
        mint=mint,
    )


def is_dust_remaining(balance_u64: int) -> bool:
    """Check if remaining balance is below dust threshold."""
    return balance_u64 < DUST_THRESHOLD_TOKENS


# Example usage
if __name__ == "__main__":
    # Test integer precision
    balance = 1001  # Odd number
    amount_50pct = calculate_swap_amount(balance, 0.5)
    print(f"Balance: {balance}, 50% = {amount_50pct}")
    assert amount_50pct == 500, f"Expected 500, got {amount_50pct}"

    # Test rounding
    balance = 1000
    amount_33pct = calculate_swap_amount(balance, 0.33)
    print(f"Balance: {balance}, 33% = {amount_33pct}")
    assert amount_33pct == 330, f"Expected 330, got {amount_33pct}"

    print("All tests passed!")
