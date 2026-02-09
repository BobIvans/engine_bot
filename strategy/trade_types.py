"""strategy/trade_types.py

Strategy-level trade type definitions for exits and signals.
These are pure data structures used by the execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExitType(Enum):
    """Type of exit signal."""
    MARKET_CLOSE = "MARKET_CLOSE"  # Full exit at market price
    PARTIAL = "PARTIAL"  # Partial exit (percentage of position)
    TRAILING_STOP_UPDATE = "TRAILING_STOP_UPDATE"  # Update trailing stop parameters


@dataclass(frozen=True)
class ExitSignal:
    """Signal to close or partially close a position.

    Attributes:
        exit_type: Type of exit (FULL, PARTIAL, UPDATE_SL).
        size_pct: Percentage of position to exit (0.0 to 1.0).
            Default 1.0 (full exit).
        trail_stop_pct: Optional trailing stop percentage (e.g., 0.05 for 5%).
        trail_activation_pct: Optional activation threshold (e.g., 0.03 for 3%).
    """
    exit_type: ExitType
    size_pct: float = 1.0
    trail_stop_pct: Optional[float] = None
    trail_activation_pct: Optional[float] = None

    def __post_init__(self):
        """Validate fields."""
        if not 0.0 < self.size_pct <= 1.0:
            raise ValueError(f"size_pct must be 0.0 < size_pct <= 1.0, got {self.size_pct}")
        if self.exit_type == ExitType.PARTIAL and self.size_pct >= 1.0:
            raise ValueError("PARTIAL exit must have size_pct < 1.0")
        if self.exit_type == ExitType.TRAILING_STOP_UPDATE:
            if self.trail_stop_pct is None:
                raise ValueError("TRAILING_STOP_UPDATE requires trail_stop_pct")


@dataclass(frozen=True)
class SimulatedTrade:
    """A trade being simulated through its lifecycle.

    Used by the simulator to track position state.
    """
    wallet: str
    mint: str
    entry_price: float
    size_remaining: float  # In tokens (not USD)
    size_initial: float  # Initial token amount
    realized_pnl: float = 0.0
    status: str = "OPEN"  # OPEN, CLOSED
    trail_stop_price: Optional[float] = None
    trail_activation_price: Optional[float] = None
