"""strategy/exits.py

PR-L.2 Chain Reaction Logic (Exit Trigger).
PR-E.2 Aggressive Exits (Partial & Trailing).

Pure functions for exit decision making:
- Partial Take Profits
- Trailing Stops
- Hard SL/TP
- Chain Reaction: Exit when leaders/smart-money panic
- Aggressive Mode: Partial exits and trailing stops for high-impulse trades

Design goals:
- Pure logic (stateless)
- Deterministic output
- Clean stdout (logs to stderr)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ExitAction(Enum):
    """Possible exit actions."""

    HOLD = "HOLD"
    PARTIAL_TP = "PARTIAL_TP"
    PARTIAL_EXIT = "PARTIAL_EXIT"  # Aggressive partial exit
    TRAIL_STOP = "TRAIL_STOP"  # Trailing stop exit
    CLOSE_FULL = "CLOSE_FULL"  # SL, TP, or TRAIL
    TIME_EXIT = "TIME_EXIT"
    MODE_SWITCH = "MODE_SWITCH"  # Switch to aggressive mode


@dataclass(frozen=True)
class PositionState:
    """Current position state for exit evaluation.

    Attributes:
        entry_price: Price at position entry.
        current_price: Current market price.
        peak_price: Highest price reached since entry (for trailing).
        elapsed_sec: Seconds since position opened.
        remaining_pct: Percentage of position remaining (1.0 = full, 0.5 = half).
        chain_reaction_score: External metric (0.0..1.0) reflecting leader/smart-money panic.
        mode: Current mode (U, S, M, L, or aggressive variants like U_aggr).
        partial_taken: Whether partial take profit has been taken (for aggressive mode).
        base_mode: Original base mode before any aggressive switch.
    """

    entry_price: float
    current_price: float
    peak_price: float
    elapsed_sec: float
    remaining_pct: float = 1.0
    chain_reaction_score: float = 0.0
    mode: str = "U"
    partial_taken: bool = False
    base_mode: str = "U"


@dataclass(frozen=True)
class ExitContext:
    """Exit context with hazard score for crash prediction.
    
    Attributes:
        position_state: Current position state.
        hazard_score: Predicted probability of exit within 60s (0.0..1.0).
        hazard_threshold: Threshold for triggering aggressive exit.
    """
    
    position_state: PositionState
    hazard_score: float = 0.0
    hazard_threshold: float = 0.35


@dataclass(frozen=True)
class ExitSignal:
    """Result of exit evaluation.

    Attributes:
        action: What to do.
        qty_pct: Percentage of remaining position to exit (0.0-1.0).
        reason: Human-readable reason for the action.
        new_mode: New mode after exit (for MODE_SWITCH action).
    """

    action: ExitAction
    qty_pct: float
    reason: str
    new_mode: Optional[str] = None


def check_aggressive_trigger(
    current_price: float,
    entry_price: float,
    elapsed_sec: float,
    current_mode: str,
    cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Check if aggressive mode trigger conditions are met.

    Args:
        current_price: Current market price.
        entry_price: Position entry price.
        elapsed_sec: Seconds since position opened.
        current_mode: Current base mode (U, S, M, L).
        cfg: Strategy config dict with aggressive settings.

    Returns:
        Dict with aggressive trigger info if conditions met, None otherwise.
        Includes: new_mode, partial_pct, trail_pct
    """
    # Check if aggressive mode is enabled
    aggressive_cfg = cfg.get("aggressive", {})
    if not aggressive_cfg.get("enabled", False):
        return None

    # Only check triggers for base modes (not already aggressive)
    if "_aggr" in current_mode:
        return None

    # Get triggers configuration
    triggers = aggressive_cfg.get("triggers", {})

    # Look for matching trigger based on current mode
    # Map base mode to aggressive mode name
    mode_to_aggr = {
        "U": "U_aggr",
        "S": "S_aggr",
        "M": "M_aggr",
        "L": "L_aggr",
    }

    aggr_mode = mode_to_aggr.get(current_mode)
    if not aggr_mode or aggr_mode not in triggers:
        return None

    trigger_cfg = triggers[aggr_mode]

    # Check conditions:
    # 1. dt_max: max time since entry
    dt_max = trigger_cfg.get("dt_max", 15)
    if elapsed_sec > dt_max:
        return None

    # 2. min_chg: minimum price change percentage
    min_chg = trigger_cfg.get("min_chg", 0.03)
    price_change_pct = (current_price - entry_price) / entry_price
    if price_change_pct < min_chg:
        return None

    # Trigger conditions met
    return {
        "new_mode": aggr_mode,
        "partial_pct": trigger_cfg.get("partial", 0.4),
        "trail_pct": trigger_cfg.get("trail", 0.12),
        "price_change_pct": price_change_pct,
        "elapsed_sec": elapsed_sec,
    }


def calculate_trailing_stop(
    peak_price: float,
    trail_pct: float,
) -> float:
    """Calculate trailing stop price based on peak price.

    Args:
        peak_price: Highest price reached since entry.
        trail_pct: Trailing stop percentage (e.g., 0.12 for 12%).

    Returns:
        Trailing stop price level.
    """
    return peak_price * (1.0 - trail_pct)


# Alias for backwards compatibility
maybe_switch_to_aggressive = check_aggressive_trigger


def maybe_switch_to_aggressive(
    current_price: float,
    entry_price: float,
    elapsed_sec: float,
    current_mode: str,
    cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Wrapper for check_aggressive_trigger for backwards compatibility."""
    return check_aggressive_trigger(
        current_price=current_price,
        entry_price=entry_price,
        elapsed_sec=elapsed_sec,
        current_mode=current_mode,
        cfg=cfg,
    )


def evaluate_exit(state: PositionState, cfg: Dict[str, Any]) -> ExitSignal:
    """Evaluate exit signals based on position state and config.

    This is a pure function that takes current state + price + config
    and returns an exit decision.

    Args:
        state: Current position state.
        cfg: Strategy config dict with exit settings.

    Returns:
        ExitSignal with action, qty_pct, and reason.
    """
    # Extract config sections
    modes = cfg.get("modes", {})
    mode_cfg = modes.get("A", {})  # Aggressive mode
    exits = mode_cfg.get("exits", {})

    # Calculate price changes
    pnl_pct = (state.current_price - state.entry_price) / state.entry_price
    peak_pnl_pct = (state.peak_price - state.entry_price) / state.entry_price

    # PR-E.2: Check Aggressive Mode triggers (before standard TP/SL)
    # Only check if not already aggressive and no partial taken
    is_aggressive = "_aggr" in state.mode
    if not is_aggressive and not state.partial_taken:
        aggr_trigger = check_aggressive_trigger(
            current_price=state.current_price,
            entry_price=state.entry_price,
            elapsed_sec=state.elapsed_sec,
            current_mode=state.mode,
            cfg=cfg,
        )
        if aggr_trigger:
            return ExitSignal(
                action=ExitAction.PARTIAL_EXIT,
                qty_pct=aggr_trigger["partial_pct"],
                reason=f"Aggressive trigger: +{aggr_trigger['price_change_pct']*100:.1f}% in {aggr_trigger['elapsed_sec']:.0f}s",
                new_mode=aggr_trigger["new_mode"],
            )

    # PR-E.2: If already aggressive mode, check trailing stop
    if is_aggressive and state.partial_taken:
        # Get aggressive config for trailing stop
        aggressive_cfg = cfg.get("aggressive", {})
        triggers = aggressive_cfg.get("triggers", {})
        aggr_mode = state.mode

        if aggr_mode in triggers:
            trail_pct = triggers[aggr_mode].get("trail", 0.12)
            trailing_stop_price = calculate_trailing_stop(
                peak_price=state.peak_price,
                trail_pct=trail_pct,
            )
            if state.current_price <= trailing_stop_price:
                return ExitSignal(
                    action=ExitAction.TRAIL_STOP,
                    qty_pct=1.0,
                    reason=f"Trailing stop: price {state.current_price:.4f} <= stop {trailing_stop_price:.4f}",
                )

    # PR-L.2: Check Chain Reaction (leaders panic)
    cr_cfg = exits.get("chain_reaction", {})
    if cr_cfg.get("enabled", False):
        threshold = cr_cfg.get("threshold", 0.5)
        if state.chain_reaction_score >= threshold:
            action = cr_cfg.get("action", "immediate_exit")
            if action == "immediate_exit":
                return ExitSignal(
                    action=ExitAction.CLOSE_FULL,
                    qty_pct=1.0,
                    reason=f"Chain Reaction: leaders panic (score={state.chain_reaction_score:.2f})"
                )
            elif action == "tighten_sl":
                # Override SL with panic_sl_pct
                panic_sl = cr_cfg.get("panic_sl_pct", -0.02)
                if pnl_pct <= panic_sl:
                    return ExitSignal(
                        action=ExitAction.CLOSE_FULL,
                        qty_pct=1.0,
                        reason=f"Chain Reaction tight SL: {pnl_pct*100:.1f}%"
                    )

    # 1. Check Hard Stop Loss
    sl_pct = exits.get("hard_sl_pct", -0.20)  # Default -20%
    if pnl_pct <= sl_pct:
        return ExitSignal(
            action=ExitAction.CLOSE_FULL,
            qty_pct=1.0,
            reason=f"Hard SL hit: {pnl_pct*100:.1f}%",
        )

    # 2. Check Hard Take Profit
    tp_pct = exits.get("hard_tp_pct", 0.50)  # Default +50%
    if pnl_pct >= tp_pct:
        return ExitSignal(
            action=ExitAction.CLOSE_FULL,
            qty_pct=1.0,
            reason=f"Hard TP hit: {pnl_pct*100:.1f}%",
        )

    # 3. Check Partial Take Profits
    partial_tps = exits.get("partial_tp", [])  # List of {trigger_pct, exit_pct}
    if state.remaining_pct > 0.1:  # Only partial if >10% remaining
        for partial in partial_tps:
            trigger_pct = partial.get("trigger_pct", 0.0)
            exit_pct = partial.get("exit_pct", 0.0)
            if pnl_pct >= trigger_pct:
                return ExitSignal(
                    action=ExitAction.PARTIAL_TP,
                    qty_pct=exit_pct,
                    reason=f"Partial TP at +{pnl_pct*100:.1f}%: sell {exit_pct*100:.0f}%",
                )

    # 4. Check Trailing Stop Activation
    trailing = exits.get("trailing", {})
    trail_activation_pct = trailing.get("activation_pct", 0.15)  # Default +15%
    trail_delta_pct = trailing.get("delta_pct", 0.05)  # Default 5% trail

    trailing_active = peak_pnl_pct >= trail_activation_pct
    if trailing_active:
        # Check if trailing stop hit
        trail_trigger_price = state.peak_price * (1.0 - trail_delta_pct)
        if state.current_price <= trail_trigger_price:
            return ExitSignal(
                action=ExitAction.CLOSE_FULL,
                qty_pct=1.0,
                reason=f"Trailing stop hit: {pnl_pct*100:.1f}% from peak {peak_pnl_pct*100:.1f}%",
            )

    # 5. Check Time Exit
    max_hold_sec = exits.get("max_hold_sec", 300)  # Default 5 min
    if state.elapsed_sec >= max_hold_sec:
        return ExitSignal(
            action=ExitAction.TIME_EXIT,
            qty_pct=1.0,
            reason=f"Max hold time: {state.elapsed_sec:.0f}s",
        )

    # Default: Hold
    return ExitSignal(
        action=ExitAction.HOLD,
        qty_pct=0.0,
        reason="No exit signal",
    )


def parse_exits_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate exits config from strategy config.

    Args:
        cfg: Full strategy config dict.

    Returns:
        Validated exits configuration dict.
    """
    defaults = {
        "hard_sl_pct": -0.20,
        "hard_tp_pct": 0.50,
        "partial_tp": [],
        "trailing": {
            "activation_pct": 0.15,
            "delta_pct": 0.05,
        },
        "max_hold_sec": 300,
    }

    modes = cfg.get("modes", {})
    mode_cfg = modes.get("A", {})
    exits = mode_cfg.get("exits", {})

    # Merge with defaults
    for key, default in defaults.items():
        if key == "trailing":
            defaults["trailing"] = {**default, **exits.get(key, {})}
        else:
            defaults[key] = exits.get(key, default)

    return defaults


@dataclass(frozen=True)
class MultiExitResult:
    """Result of multi-step exit simulation.

    Attributes:
        final_action: Final exit action taken.
        total_pnl_pct: Sum of all realized PnL percentages.
        realized_parts: List of (action, pnl_pct, qty_pct) tuples.
        peak_price: Peak price reached during simulation.
        exit_reason: Reason for final exit.
    """

    final_action: ExitAction
    total_pnl_pct: float
    realized_parts: List[Tuple[ExitAction, float, float]]
    peak_price: float
    exit_reason: str


def simulate_multi_exit(
    entry_price: float,
    price_path: List[float],
    cfg: Dict[str, Any],
) -> MultiExitResult:
    """Simulate multi-step exits along a price path.

    Args:
        entry_price: Position entry price.
        price_path: List of future prices (in order).
        cfg: Strategy config dict.

    Returns:
        MultiExitResult with all realized parts summed.
    """
    # Initialize state
    remaining_pct = 1.0
    realized_pnl_parts: List[Tuple[ExitAction, float, float]] = []
    peak_price = entry_price
    final_action = ExitAction.HOLD
    exit_reason = "No exit triggered"

    # Initialize state for evaluate_exit
    for i, current_price in enumerate(price_path):
        # Update peak price
        if current_price > peak_price:
            peak_price = current_price

        state = PositionState(
            entry_price=entry_price,
            current_price=current_price,
            peak_price=peak_price,
            elapsed_sec=float(i),  # 1 tick = 1 second
            remaining_pct=remaining_pct,
        )

        signal = evaluate_exit(state, cfg)

        if signal.action == ExitAction.HOLD:
            continue

        # Calculate PnL for this exit
        pnl_pct = (current_price - entry_price) / entry_price
        qty_pct = signal.qty_pct * remaining_pct  # Scale by remaining

        realized_pnl_parts.append((signal.action, pnl_pct, qty_pct))

        if signal.action == ExitAction.PARTIAL_TP or signal.action == ExitAction.PARTIAL_EXIT:
            # Reduce remaining position
            remaining_pct -= signal.qty_pct
            if remaining_pct <= 0.01:  # Less than 1% remaining
                final_action = ExitAction.CLOSE_FULL
                exit_reason = signal.reason + " (final close)"
                break
        else:
            # Full exit
            final_action = signal.action
            exit_reason = signal.reason
            break

    # Calculate total weighted PnL
    total_pnl_pct = sum(pnl * qty for _, pnl, qty in realized_pnl_parts)

    return MultiExitResult(
        final_action=final_action,
        total_pnl_pct=total_pnl_pct,
        realized_parts=realized_pnl_parts,
        peak_price=peak_price,
        exit_reason=exit_reason,
    )
