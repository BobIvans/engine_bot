"""strategy/state.py - Portfolio State Definition

Defines the PortfolioState data class and helper structures for tracking
the trading portfolio's current state (bankroll, positions, PnL, cooldown).

This state is the "memory" of the strategy, passed to decision functions
for Risk Gates verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class Position:
    """Single position tracking."""
    token_mint: str
    entry_price: float
    size_usd: float
    wallet_address: str
    opened_at: int  # Unix timestamp


@dataclass
class PortfolioState:
    """Complete portfolio state snapshot.
    
    This is the "memory" of the strategy - it stores:
    - Current bankroll and PnL
    - Open positions and exposure tracking
    - Cooldown status (for Daily Loss Limit)
    
    All fields are serializable to JSON/Dict for checkpoint recovery.
    """
    # Core capital tracking
    bankroll_usd: float
    
    # Daily PnL tracking (reset at start of day)
    daily_pnl_usd: float = 0.0
    
    # Drawdown tracking (for Kill-Switch)
    total_drawdown_pct: float = 0.0
    peak_bankroll_usd: float = 0.0
    
    # Position tracking
    open_positions: Dict[str, Position] = field(default_factory=dict)
    open_position_count: int = 0
    
    # Exposure limits tracking
    exposure_by_token: Dict[str, float] = field(default_factory=dict)
    exposure_by_source_wallet: Dict[str, float] = field(default_factory=dict)
    
    # Cooldown state (triggered by daily loss limit breach)
    cooldown_active: bool = False
    cooldown_until_ts: Optional[int] = None  # Unix timestamp
    
    # Metadata
    last_updated_ts: int = 0
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to serializable dictionary."""
        return {
            "bankroll_usd": self.bankroll_usd,
            "daily_pnl_usd": self.daily_pnl_usd,
            "total_drawdown_pct": self.total_drawdown_pct,
            "peak_bankroll_usd": self.peak_bankroll_usd,
            "open_positions": {
                pos_id: {
                    "token_mint": p.token_mint,
                    "entry_price": p.entry_price,
                    "size_usd": p.size_usd,
                    "wallet_address": p.wallet_address,
                    "opened_at": p.opened_at,
                }
                for pos_id, p in self.open_positions.items()
            },
            "open_position_count": self.open_position_count,
            "exposure_by_token": self.exposure_by_token,
            "exposure_by_source_wallet": self.exposure_by_source_wallet,
            "cooldown_active": self.cooldown_active,
            "cooldown_until_ts": self.cooldown_until_ts,
            "last_updated_ts": self.last_updated_ts,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> PortfolioState:
        """Reconstruct from dictionary."""
        open_positions = {}
        for pos_id, pos_data in data.get("open_positions", {}).items():
            open_positions[pos_id] = Position(
                token_mint=pos_data["token_mint"],
                entry_price=pos_data["entry_price"],
                size_usd=pos_data["size_usd"],
                wallet_address=pos_data["wallet_address"],
                opened_at=pos_data["opened_at"],
            )
        
        return cls(
            bankroll_usd=data["bankroll_usd"],
            daily_pnl_usd=data.get("daily_pnl_usd", 0.0),
            total_drawdown_pct=data.get("total_drawdown_pct", 0.0),
            peak_bankroll_usd=data.get("peak_bankroll_usd", data["bankroll_usd"]),
            open_positions=open_positions,
            open_position_count=data.get("open_position_count", len(open_positions)),
            exposure_by_token=data.get("exposure_by_token", {}),
            exposure_by_source_wallet=data.get("exposure_by_source_wallet", {}),
            cooldown_active=data.get("cooldown_active", False),
            cooldown_until_ts=data.get("cooldown_until_ts"),
            last_updated_ts=data.get("last_updated_ts", 0),
        )
    
    @classmethod
    def initial(cls, initial_bankroll_usd: float, now_ts: int = 0) -> PortfolioState:
        """Create initial empty state."""
        return cls(
            bankroll_usd=initial_bankroll_usd,
            peak_bankroll_usd=initial_bankroll_usd,
            last_updated_ts=now_ts,
        )
    
    def get_total_exposure(self) -> float:
        """Get total exposure across all tokens."""
        return sum(self.exposure_by_token.values())
    
    def get_token_exposure(self, token_mint: str) -> float:
        """Get exposure for a specific token."""
        return self.exposure_by_token.get(token_mint, 0.0)
    
    def get_wallet_exposure(self, wallet_address: str) -> float:
        """Get exposure for a specific source wallet."""
        return self.exposure_by_source_wallet.get(wallet_address, 0.0)


@dataclass
class StateUpdateParams:
    """Configuration parameters for state transitions."""
    # Cooldown settings
    max_daily_loss_usd: float = 500.0  # Trigger cooldown if daily loss exceeds this
    cooldown_duration_sec: int = 3600  # 1 hour cooldown
    
    # Position limits
    max_positions: int = 10
    max_token_concentration_pct: float = 0.25  # Max 25% in single token
    max_wallet_concentration_pct: float = 0.50  # Max 50% from single wallet
    
    def check_daily_loss_limit(self, daily_pnl: float) -> bool:
        """Check if daily loss exceeds limit."""
        return daily_pnl < -self.max_daily_loss_usd


# Helper functions for state validation
def can_open_position(state: PortfolioState, params: StateUpdateParams) -> tuple:
    """Check if a new position can be opened.
    
    Returns:
        (can_open: bool, reason: str)
    """
    if state.cooldown_active:
        return False, "cooldown_active"
    
    if state.open_position_count >= params.max_positions:
        return False, "max_positions_reached"
    
    return True, ""


def can_increase_exposure(
    state: PortfolioState,
    token_mint: str,
    wallet_address: str,
    additional_usd: float,
    params: StateUpdateParams,
) -> tuple:
    """Check if increasing exposure is within limits.
    
    Returns:
        (can_increase: bool, reason: str)
    """
    # Check token concentration: new token exposure vs total portfolio value
    current_token_exposure = state.get_token_exposure(token_mint)
    new_token_exposure = current_token_exposure + additional_usd
    
    # Total portfolio value = bankroll + new total exposure
    new_total_exposure = state.get_total_exposure() + additional_usd
    total_portfolio_value = state.bankroll_usd + new_total_exposure
    
    if total_portfolio_value > 0:
        new_token_pct = new_token_exposure / total_portfolio_value
        if new_token_pct > params.max_token_concentration_pct:
            return False, "token_concentration_exceeded"
    
    # Check wallet concentration: new wallet exposure vs total portfolio value
    current_wallet_exposure = state.get_wallet_exposure(wallet_address)
    new_wallet_exposure = current_wallet_exposure + additional_usd
    
    if total_portfolio_value > 0:
        new_wallet_pct = new_wallet_exposure / total_portfolio_value
        if new_wallet_pct > params.max_wallet_concentration_pct:
            return False, "wallet_concentration_exceeded"
    
    return True, ""
