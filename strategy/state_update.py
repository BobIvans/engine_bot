"""strategy/state_update.py - Pure State Transition Functions

Pure functions for updating PortfolioState based on trading events.
遵循 "No side-effects" 规则: (OldState, Event) -> NewState.

All functions are deterministic and testable without mocks.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Tuple

from strategy.state import (
    PortfolioState,
    Position,
    StateUpdateParams,
    can_open_position,
    can_increase_exposure,
)


def transition_on_entry(
    state: PortfolioState,
    signal_id: str,
    token_mint: str,
    wallet_address: str,
    size_usd: float,
    fill_price: float,
    now_ts: int,
    params: StateUpdateParams,
) -> Tuple[PortfolioState, str]:
    """Process a position entry (buy) event.
    
    Pure function: creates new state without modifying input.
    
    Args:
        state: Current portfolio state.
        signal_id: Unique identifier for the signal/trade.
        token_mint: Token address (mint).
        wallet_address: Source wallet address.
        size_usd: Position size in USD.
        fill_price: Execution fill price.
        now_ts: Current timestamp.
        params: State update parameters.
    
    Returns:
        Tuple of (new_state, error_message). error_message is empty if successful.
    """
    # Check if we can open a new position
    can_open, reason = can_open_position(state, params)
    if not can_open:
        return state, reason
    
    # Check exposure limits
    can_increase, exp_reason = can_increase_exposure(
        state, token_mint, wallet_address, size_usd, params
    )
    if not can_increase:
        return state, exp_reason
    
    # Deduct from bankroll (simplified: assume full equity model)
    new_bankroll = state.bankroll_usd - size_usd
    
    # Create new position
    position = Position(
        token_mint=token_mint,
        entry_price=fill_price,
        size_usd=size_usd,
        wallet_address=wallet_address,
        opened_at=now_ts,
    )
    
    # Build new state dicts
    new_open_positions = dict(state.open_positions)
    new_open_positions[signal_id] = position
    
    new_exposure_by_token = dict(state.exposure_by_token)
    new_exposure_by_token[token_mint] = new_exposure_by_token.get(token_mint, 0.0) + size_usd
    
    new_exposure_by_wallet = dict(state.exposure_by_source_wallet)
    new_exposure_by_wallet[wallet_address] = new_exposure_by_wallet.get(wallet_address, 0.0) + size_usd
    
    # Create new state
    new_state = replace(state)
    new_state.bankroll_usd = new_bankroll
    new_state.open_positions = new_open_positions
    new_state.open_position_count = len(new_open_positions)
    new_state.exposure_by_token = new_exposure_by_token
    new_state.exposure_by_source_wallet = new_exposure_by_wallet
    new_state.last_updated_ts = now_ts
    
    return new_state, ""


def transition_on_exit(
    state: PortfolioState,
    signal_id: str,
    token_mint: str,
    wallet_address: str,
    exit_price: float,
    pnl_usd: float,
    now_ts: int,
) -> Tuple[PortfolioState, str]:
    """Process a position exit (sell) event.
    
    Pure function: creates new state without modifying input.
    
    Args:
        state: Current portfolio state.
        signal_id: Position/signal identifier to close.
        token_mint: Token address (mint).
        wallet_address: Source wallet address.
        exit_price: Execution exit price.
        pnl_usd: Realized PnL (positive for profit, negative for loss).
        now_ts: Current timestamp.
    
    Returns:
        Tuple of (new_state, error_message). error_message is empty if successful.
    """
    # Check if position exists
    if signal_id not in state.open_positions:
        return state, f"position_not_found:{signal_id}"
    
    position = state.open_positions[signal_id]
    
    # Update bankroll with PnL (return position size + PnL)
    new_bankroll = state.bankroll_usd + position.size_usd + pnl_usd
    
    # Update daily PnL
    new_daily_pnl = state.daily_pnl_usd + pnl_usd
    
    # Update peak bankroll if we're at a new high
    new_peak = state.peak_bankroll_usd
    if new_bankroll > new_peak:
        new_peak = new_bankroll
    
    # Calculate drawdown
    if new_peak > 0:
        new_drawdown_pct = (new_peak - new_bankroll) / new_peak
    else:
        new_drawdown_pct = 1.0  # Full drawdown if no peak
    
    # Remove position from tracking
    new_open_positions = dict(state.open_positions)
    del new_open_positions[signal_id]
    
    # Reduce exposure tracking
    position_size = position.size_usd
    
    new_exposure_by_token = dict(state.exposure_by_token)
    current_token_exp = new_exposure_by_token.get(token_mint, 0.0)
    new_exposure_by_token[token_mint] = max(0.0, current_token_exp - position_size)
    if new_exposure_by_token[token_mint] == 0:
        del new_exposure_by_token[token_mint]
    
    new_exposure_by_wallet = dict(state.exposure_by_source_wallet)
    current_wallet_exp = new_exposure_by_wallet.get(wallet_address, 0.0)
    new_exposure_by_wallet[wallet_address] = max(0.0, current_wallet_exp - position_size)
    if new_exposure_by_wallet.get(wallet_address, 0.0) == 0:
        del new_exposure_by_wallet[wallet_address]
    
    # Create new state
    new_state = replace(state)
    new_state.bankroll_usd = new_bankroll
    new_state.daily_pnl_usd = new_daily_pnl
    new_state.total_drawdown_pct = new_drawdown_pct
    new_state.peak_bankroll_usd = new_peak
    new_state.open_positions = new_open_positions
    new_state.open_position_count = len(new_open_positions)
    new_state.exposure_by_token = new_exposure_by_token
    new_state.exposure_by_source_wallet = new_exposure_by_wallet
    new_state.last_updated_ts = now_ts
    
    return new_state, ""


def update_cooldown(
    state: PortfolioState,
    params: StateUpdateParams,
    now_ts: int,
) -> PortfolioState:
    """Check daily loss limit and update cooldown status.
    
    Pure function: creates new state without modifying input.
    
    Args:
        state: Current portfolio state.
        params: State update parameters with cooldown settings.
        now_ts: Current timestamp.
    
    Returns:
        New state with updated cooldown status.
    """
    # Check if we need to activate cooldown
    should_cooldown = params.check_daily_loss_limit(state.daily_pnl_usd)
    
    new_state = replace(state)
    
    if should_cooldown and not state.cooldown_active:
        # Activate cooldown
        new_state.cooldown_active = True
        new_state.cooldown_until_ts = now_ts + params.cooldown_duration_sec
        new_state.last_updated_ts = now_ts
    elif not should_cooldown and state.cooldown_active:
        # Check if cooldown has expired
        if state.cooldown_until_ts and now_ts >= state.cooldown_until_ts:
            new_state.cooldown_active = False
            new_state.cooldown_until_ts = None
            new_state.last_updated_ts = now_ts
    
    return new_state


def reset_daily_pnl(
    state: PortfolioState,
    now_ts: int,
) -> PortfolioState:
    """Reset daily PnL counter (call at start of new trading day).
    
    Pure function: creates new state without modifying input.
    
    Args:
        state: Current portfolio state.
        now_ts: Current timestamp.
    
    Returns:
        New state with daily PnL reset to 0.
    """
    new_state = replace(state)
    new_state.daily_pnl_usd = 0.0
    new_state.last_updated_ts = now_ts
    return new_state


def apply_fill_event(
    state: PortfolioState,
    fill_event: Dict[str, any],
    params: StateUpdateParams,
) -> Tuple[PortfolioState, str]:
    """Apply a fill event (entry or exit) to state.
    
    Unified handler that detects entry vs exit and routes appropriately.
    
    Args:
        state: Current portfolio state.
        fill_event: Fill event dict with fields:
            - signal_id: Unique identifier
            - side: "BUY" or "SELL"
            - token_mint: Token address
            - wallet_address: Source wallet
            - size_usd: Position size
            - price: Fill price
            - pnl_usd: For SELL only
            - ts: Timestamp
        params: State update parameters.
    
    Returns:
        Tuple of (new_state, error_message).
    """
    signal_id = fill_event.get("signal_id", "unknown")
    side = fill_event.get("side", "BUY")
    token_mint = fill_event.get("token_mint", "")
    wallet_address = fill_event.get("wallet_address", "")
    size_usd = fill_event.get("size_usd", 0.0)
    price = fill_event.get("price", 0.0)
    pnl_usd = fill_event.get("pnl_usd", 0.0)
    ts = fill_event.get("ts", 0)
    
    if side == "BUY":
        return transition_on_entry(
            state=state,
            signal_id=signal_id,
            token_mint=token_mint,
            wallet_address=wallet_address,
            size_usd=size_usd,
            fill_price=price,
            now_ts=ts,
            params=params,
        )
    elif side == "SELL":
        return transition_on_exit(
            state=state,
            signal_id=signal_id,
            token_mint=token_mint,
            wallet_address=wallet_address,
            exit_price=price,
            pnl_usd=pnl_usd,
            now_ts=ts,
        )
    else:
        return state, f"unknown_side:{side}"


# Self-test when run directly
if __name__ == "__main__":
    import json
    
    # Create initial state
    initial = PortfolioState.initial(initial_bankroll_usd=10000.0, now_ts=1000)
    params = StateUpdateParams(max_daily_loss_usd=500.0)
    
    print("Initial State:")
    print(f"  Bankroll: ${initial.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${initial.daily_pnl_usd:.2f}")
    print(f"  Positions: {initial.open_position_count}")
    print()
    
    # Test 1: Entry
    new_state, err = transition_on_entry(
        state=initial,
        signal_id="TRADE001",
        token_mint="SOLabc123",
        wallet_address="WalletA",
        size_usd=1000.0,
        fill_price=0.0002,
        now_ts=1001,
        params=params,
    )
    
    print("After Entry (BUY $1000 SOL):")
    print(f"  Bankroll: ${new_state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${new_state.daily_pnl_usd:.2f}")
    print(f"  Positions: {new_state.open_position_count}")
    print(f"  Exposure by token: {new_state.exposure_by_token}")
    print()
    
    # Test 2: Exit with profit
    profit_state, err = transition_on_exit(
        state=new_state,
        signal_id="TRADE001",
        token_mint="SOLabc123",
        wallet_address="WalletA",
        exit_price=0.00025,
        pnl_usd=250.0,  # 25% profit
        now_ts=1002,
    )
    
    print("Exit with Profit (+$250):")
    print(f"  Bankroll: ${profit_state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${profit_state.daily_pnl_usd:.2f}")
    print(f"  Positions: {profit_state.open_position_count}")
    print()
    
    # Test 3: Exit with loss triggering cooldown
    # Reset and create new entry
    loss_entry_state, _ = transition_on_entry(
        state=initial,
        signal_id="TRADE002",
        token_mint="RAYxyz789",
        wallet_address="WalletB",
        size_usd=1000.0,
        fill_price=0.001,
        now_ts=1003,
        params=params,
    )
    
    loss_state, err = transition_on_exit(
        state=loss_entry_state,
        signal_id="TRADE002",
        token_mint="RAYxyz789",
        wallet_address="WalletB",
        exit_price=0.0005,
        pnl_usd=-600.0,  # 60% loss - exceeds $500 daily limit
        now_ts=1004,
    )
    
    # Check cooldown
    final_state = update_cooldown(loss_state, params, now_ts=1004)
    
    print("Exit with Loss (-$600, exceeds $500 limit):")
    print(f"  Bankroll: ${final_state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${final_state.daily_pnl_usd:.2f}")
    print(f"  Cooldown Active: {final_state.cooldown_active}")
    print()
    
    # Test serialization
    print("Serialization Test:")
    serialized = final_state.to_dict()
    print(json.dumps(serialized, indent=2))
    
    # Test deserialization
    restored = PortfolioState.from_dict(serialized)
    print(f"\nRestored State:")
    print(f"  Bankroll: ${restored.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${restored.daily_pnl_usd:.2f}")
    print(f"  Cooldown: {restored.cooldown_active}")
