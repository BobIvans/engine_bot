"""
strategy/aggr_logic.py - Aggressive Execution Switch Logic

Pure logic for switching open positions from Base mode to Aggressive mode.
Evaluates already-opened positions and decides whether to enable trailing/runner mode.

HARD RULES:
1. Purity: Only pure functions. Input: Snapshot + Params. Output: (NewMode | None, Reason).
2. Safety First: Switch IMPOSSIBLE if passes_aggressive_safety returns False.
3. Config Driven: All thresholds from StrategyParams, no magic numbers.
4. One-way: Only Base -> Aggr transition. No reverse.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum


class AggressiveMode(Enum):
    """Aggressive mode variants."""
    U_AGGR = "U_aggr"
    S_AGGR = "S_aggr"
    M_AGGR = "M_aggr"
    L_AGGR = "L_aggr"


class BaseMode(Enum):
    """Base mode variants (before aggressive switch)."""
    U = "U"
    S = "S"
    M = "M"
    L = "L"


@dataclass
class PositionSnapshot:
    """Position state snapshot."""
    position_id: str
    token_address: str
    wallet_address: str
    base_mode: str  # U, S, M, L
    entry_price: float
    current_price: float
    position_size: float
    entry_time_sec: float  # Time since entry in seconds
    current_roi: float  # Current ROI as fraction (0.1 = 10%)


@dataclass
class WalletProfile:
    """Wallet profile data (for safety checks)."""
    wallet_address: str
    winrate: float
    roi_mean: float
    trade_count: int
    smart_money_score: float


@dataclass
class TokenSnapshot:
    """Token snapshot (for liquidity checks)."""
    token_address: str
    symbol: str
    liquidity_usd: float
    spread_bps: int  # Bid-ask spread in basis points


@dataclass
class PortfolioState:
    """Current portfolio state."""
    total_value_usd: float
    aggr_positions_count: int
    aggr_exposure_usd: float
    daily_aggr_count: int


@dataclass
class AggressiveSwitchParams:
    """
    Configuration for aggressive switch logic.
    All thresholds are configurable via StrategyParams.
    """
    # Safety thresholds
    min_wallet_roi_for_aggr: float = 0.25
    min_wallet_winrate_for_aggr: float = 0.5
    min_token_liquidity_usd: float = 50000.0
    max_spread_bps: int = 100  # 1% max spread
    max_aggr_exposure_pct: float = 0.3  # Max 30% portfolio in aggressive
    max_daily_aggr_trades: int = 10
    
    # Impulse triggers (mode -> trigger config)
    triggers: Dict[str, Dict] = None
    
    def __post_init__(self):
        """Set default triggers if not provided."""
        if self.triggers is None:
            self.triggers = {
                "U": {
                    "dt_sec_max": 12,  # Max 12 seconds
                    "min_chg_pct": 0.03  # Min 3% change
                },
                "S": {
                    "dt_sec_max": 20,
                    "min_chg_pct": 0.02
                },
                "M": {
                    "dt_sec_max": 30,
                    "min_chg_pct": 0.015
                },
                "L": {
                    "dt_sec_max": 60,
                    "min_chg_pct": 0.01
                }
            }


def passes_aggressive_safety(
    wallet: WalletProfile,
    token: TokenSnapshot,
    portfolio: PortfolioState,
    params: AggressiveSwitchParams
) -> Tuple[bool, Optional[str]]:
    """
    Check if position passes aggressive mode safety gates.
    
    Returns:
        Tuple of (passed: bool, reason: Optional[str])
    """
    # Wallet ROI check
    if wallet.roi_mean < params.min_wallet_roi_for_aggr:
        return False, "aggr_wallet_roi_low"
    
    # Wallet winrate check
    if wallet.winrate < params.min_wallet_winrate_for_aggr:
        return False, "aggr_wallet_winrate_low"
    
    # Token liquidity check
    if token.liquidity_usd < params.min_token_liquidity_usd:
        return False, "aggr_liquidity_low"
    
    # Spread check
    if token.spread_bps > params.max_spread_bps:
        return False, "aggr_spread_high"
    
    # Portfolio exposure check
    if params.max_aggr_exposure_pct > 0:
        exposure_ratio = portfolio.aggr_exposure_usd / portfolio.total_value_usd
        if exposure_ratio >= params.max_aggr_exposure_pct:
            return False, "aggr_exposure_limit"
    
    # Daily limit check
    if portfolio.daily_aggr_count >= params.max_daily_aggr_trades:
        return False, "aggr_daily_trade_limit"
    
    return True, None


def maybe_switch_to_aggressive(
    position: PositionSnapshot,
    wallet: WalletProfile,
    token: TokenSnapshot,
    portfolio: PortfolioState,
    params: AggressiveSwitchParams
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide whether to switch from Base mode to Aggressive mode.
    
    Algorithm:
    1. Check Safety First (IMPOSSIBLE if fails).
    2. Match base mode to trigger config.
    3. Check dt_sec <= trigger['dt_sec_max'] (Impulse speed).
    4. Check price_change >= trigger['min_chg_pct'].
    5. Return new mode (e.g., "U_aggr") or None.
    
    Returns:
        Tuple of (new_mode: Optional[str], reason: Optional[str])
        - new_mode: Mode to switch to (e.g., "U_aggr") or None
        - reason: Reason for decision (for logging)
    """
    # Step 1: Safety First
    safety_passed, safety_reason = passes_aggressive_safety(
        wallet, token, portfolio, params
    )
    
    if not safety_passed:
        return None, safety_reason
    
    # Step 2: Get trigger for base mode
    base_mode = position.base_mode.upper()
    trigger = params.triggers.get(base_mode)
    
    if trigger is None:
        return None, "aggr_no_trigger"
    
    # Step 3: Check impulse speed (time constraint)
    if position.entry_time_sec > trigger["dt_sec_max"]:
        return None, "aggr_time_expired"
    
    # Step 4: Check price change percentage
    price_change_pct = position.current_roi  # ROI already represents % change
    
    if price_change_pct < trigger["min_chg_pct"]:
        return None, "aggr_insufficient_impulse"
    
    # Step 5: Determine new mode
    new_mode_map = {
        "U": AggressiveMode.U_AGGR.value,
        "S": AggressiveMode.S_AGGR.value,
        "M": AggressiveMode.M_AGGR.value,
        "L": AggressiveMode.L_AGGR.value
    }
    
    new_mode = new_mode_map.get(base_mode)
    
    if new_mode:
        return new_mode, "aggr_triggered"
    
    return None, "aggr_unknown_mode"


# Convenience function
def should_switch(
    position: PositionSnapshot,
    wallet: WalletProfile,
    token: TokenSnapshot,
    portfolio: PortfolioState,
    params: Optional[AggressiveSwitchParams] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Convenience function: returns (should_switch, new_mode, reason).
    
    Args:
        position: Current position state
        wallet: Wallet profile
        token: Token snapshot
        portfolio: Portfolio state
        params: Aggressive switch params (uses defaults if None)
    
    Returns:
        Tuple of (should_switch: bool, new_mode: Optional[str], reason: Optional[str])
    """
    params = params or AggressiveSwitchParams()
    new_mode, reason = maybe_switch_to_aggressive(
        position, wallet, token, portfolio, params
    )
    return (new_mode is not None, new_mode, reason)


if __name__ == "__main__":
    # Quick self-test
    print("Aggressive Switch Logic Self-Test")
    print("=" * 50)
    
    params = AggressiveSwitchParams()
    
    # Test Case 1: Success - U mode, fast impulse
    position_success = PositionSnapshot(
        position_id="pos_001",
        token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        wallet_address="smart_wallet",
        base_mode="U",
        entry_price=100.0,
        current_price=104.0,
        position_size=100.0,
        entry_time_sec=10.0,
        current_roi=0.04
    )
    
    wallet_success = WalletProfile(
        wallet_address="smart_wallet",
        winrate=0.7,
        roi_mean=0.5,
        trade_count=20,
        smart_money_score=0.8
    )
    
    token_success = TokenSnapshot(
        token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        symbol="SOL",
        liquidity_usd=100000,
        spread_bps=50
    )
    
    portfolio_success = PortfolioState(
        total_value_usd=10000.0,
        aggr_positions_count=0,
        aggr_exposure_usd=0.0,
        daily_aggr_count=0
    )
    
    should, mode, reason = should_switch(
        position_success, wallet_success, token_success, portfolio_success, params
    )
    print(f"Success case: should_switch={should}, mode={mode}, reason={reason}")
    
    # Test Case 2: Too slow - U mode, 20s elapsed
    position_slow = PositionSnapshot(
        position_id="pos_002",
        token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        wallet_address="smart_wallet",
        base_mode="U",
        entry_price=100.0,
        current_price=104.0,
        position_size=100.0,
        entry_time_sec=20.0,  # Too slow!
        current_roi=0.04
    )
    
    should2, mode2, reason2 = should_switch(
        position_slow, wallet_success, token_success, portfolio_success, params
    )
    print(f"\nToo slow case: should_switch={should2}, mode={mode2}, reason={reason2}")
    
    # Test Case 3: Safety block - low wallet ROI
    wallet_low_roi = WalletProfile(
        wallet_address="bad_wallet",
        winrate=0.7,
        roi_mean=0.1,  # Below min_wallet_roi_for_aggr (0.25)
        trade_count=20,
        smart_money_score=0.5
    )
    
    position_fast = PositionSnapshot(
        position_id="pos_003",
        token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        wallet_address="bad_wallet",
        base_mode="U",
        entry_price=100.0,
        current_price=110.0,  # +10%!
        position_size=100.0,
        entry_time_sec=5.0,
        current_roi=0.10
    )
    
    should3, mode3, reason3 = should_switch(
        position_fast, wallet_low_roi, token_success, portfolio_success, params
    )
    print(f"\nSafety block case: should_switch={should3}, mode={mode3}, reason={reason3}")
