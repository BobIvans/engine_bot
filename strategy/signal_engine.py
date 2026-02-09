"""strategy/signal_engine.py

PR-S.1 Signal Engine v1 (Pure Logic Separation).

Centralizes entry decision logic:
- Applies hard gates
- Resolves trading mode
- Computes edge (+EV calculation)
- Returns SignalDecision

Pure function: no I/O, no ClickHouse, no datetime.now()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from integration.gates import GateDecision, apply_gates
from integration.mode_registry import resolve_modes
from integration.reject_reasons import STRATEGY_LOW_EDGE
from integration.sim_preflight import compute_edge_bps
from integration.token_snapshot_store import TokenSnapshot
from integration.trade_types import Trade
from integration.wallet_profile_store import WalletProfile
from strategy.honeypot_filter import check_security
from strategy.mode_selector import select_mode
from strategy.probing import evaluate_probe
from strategy.regime import adjust_min_edge_bps


@dataclass(frozen=True)
class SignalDecision:
    """Structured result of entry decision logic.

    Attributes:
        should_enter: True if trade passes all gates and has sufficient edge.
        reason: Human-readable reason for rejection or 'entry_ok' for entry.
               e.g., 'min_liquidity_fail', 'strategy_low_edge', 'entry_ok'
        mode: Resolved mode name (e.g., 'U', 'S', 'A').
        edge_bps: Computed edge in basis points (can be negative).
        calc_details: Detailed breakdown of calculations for debugging/audit.
    """
    should_enter: bool
    reason: Optional[str]  # e.g., 'min_liquidity_fail' or 'strategy_low_edge'
    mode: str              # e.g., 'U', 'S' ...
    edge_bps: int
    calc_details: Dict[str, Any]


def decide_entry(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
    cfg: Dict[str, Any],
    p_model: Optional[float] = None,
    risk_regime: float = 0.0,  # PR-F.3: Polymarket regime scalar [-1, 1]
) -> SignalDecision:
    """Determine whether to emit an entry signal for the given trade.

    This is a pure function that:
    1. Checks if this is an entry candidate (BUY side)
    2. Applies honeypot/security hard gate (PR-B.3)
    3. Applies hard gates (token, wallet filters)
    4. Resolves the trading mode from config
    5. Computes the edge (+EV) based on winrate, TP/SL, and costs
    6. Compares edge against minimum threshold

    Args:
        trade: Normalized trade event (must be BUY side for entry decisions).
        snapshot: Optional token snapshot for gate checks.
        wallet_profile: Optional wallet profile for edge calculation.
        cfg: Strategy configuration dict (supports 'min_edge_bps', 'modes', etc.).

    Returns:
        SignalDecision with entry recommendation and reasoning.
    """
    calc_details: Dict[str, Any] = {
        "mint": trade.mint,
        "wallet": trade.wallet,
        "tx_hash": trade.tx_hash,
        "side": trade.side,
        "p_model": p_model,
        "risk_regime": risk_regime,  # PR-F.3
    }

    # Step 1: Check if this is an entry candidate (BUY side)
    if trade.side.upper() != "BUY":
        return SignalDecision(
            should_enter=False,
            reason="not_buy_side",
            mode="",
            edge_bps=0,
            calc_details=calc_details,
        )

    # Step 2: Apply honeypot/security hard gate (PR-B.3)
    security_passed, security_reason = check_security(snapshot, cfg)
    calc_details["security_check"] = {
        "passed": security_passed,
        "reason": security_reason,
    }
    
    if not security_passed:
        return SignalDecision(
            should_enter=False,
            reason=security_reason or "security_failure",
            mode="",
            edge_bps=0,
            calc_details=calc_details,
        )

    # Step 3: Apply hard gates
    gate_decision = apply_gates(cfg=cfg, trade=trade, snapshot=snapshot)
    calc_details["gate_decision"] = {
        "passed": gate_decision.passed,
        "reasons": gate_decision.reasons,
        "details": gate_decision.details,
    }

    if not gate_decision.passed:
        return SignalDecision(
            should_enter=False,
            reason=gate_decision.primary_reason or "gate_failure",
            mode="",
            edge_bps=0,
            calc_details=calc_details,
        )

    # Step 4: Resolve mode from config
    modes = resolve_modes(cfg)
    mode_name, mode_reason = _extract_mode(
        trade=trade,
        wallet_profile=wallet_profile,
        snapshot=snapshot,
        modes=modes,
        cfg=cfg
    )
    calc_details["resolved_mode"] = mode_name
    calc_details["mode_selection_reason"] = mode_reason

    # Get mode configuration
    mode_cfg = modes.get(mode_name, {})
    calc_details["mode_config"] = mode_cfg

    # Step 5: Compute edge (+EV) if wallet profile is available
    edge_bps = 0
    if wallet_profile is not None or p_model is not None:
        edge_bps = compute_edge_bps(
            trade=trade,
            token_snap=snapshot,
            wallet_profile=wallet_profile,
            cfg=cfg,
            mode_name=mode_name,
            p_model=p_model,
        )
    else:
        # No wallet profile - cannot compute edge
        calc_details["edge_warning"] = "missing_wallet_profile"

    calc_details["edge_bps_raw"] = edge_bps

    # Step 6: Compare against minimum edge threshold
    # PR-F.3: Adjust threshold based on Polymarket regime
    # PR-Y.5: Use edge_threshold_base (float) if available, else fallback to min_edge_bps (int)
    
    # Check if new float config is present
    signals_cfg = cfg.get("signals", {})
    if "edge_threshold_base" in signals_cfg:
        base_threshold_float = float(signals_cfg["edge_threshold_base"])
        # Convert to BPS for comparison (0.05 -> 500)
        base_min_edge_bps = int(base_threshold_float * 10000)
    else:
        # Fallback to legacy config
        base_min_edge_bps = int(cfg.get("min_edge_bps", 0))

    regime_cfg = cfg.get("regime", {})
    adjustment_cfg = cfg.get("adjustments", {})

    # Apply regime adjustment to minimum edge
    min_edge_bps = adjust_min_edge_bps(
        base_min_edge=base_min_edge_bps,
        regime=risk_regime,
        cfg=adjustment_cfg,
    )
    calc_details["min_edge_bps"] = {
        "base": base_min_edge_bps,
        "effective": min_edge_bps,
        "risk_regime": risk_regime,
    }

    if edge_bps < min_edge_bps:
        return SignalDecision(
            should_enter=False,
            reason=STRATEGY_LOW_EDGE,
            mode=mode_name,
            edge_bps=edge_bps,
            calc_details=calc_details,
        )

    # All checks passed - emit entry signal
    # Step 7: Evaluate probe trade requirement
    probe_result = evaluate_probe(
        snapshot=snapshot,
        trade_size_usd=trade.size_usd,
        cfg=cfg,
    )
    calc_details["probe"] = {
        "is_probe": probe_result.is_probe,
        "original_size_usd": trade.size_usd,
        "suggested_size_usd": probe_result.size_usd,
        "reason": probe_result.reason,
    }

    return SignalDecision(
        should_enter=True,
        reason="entry_ok",
        mode=mode_name,
        edge_bps=edge_bps,
        calc_details=calc_details,
    )


def _extract_mode(
    trade: Trade,
    wallet_profile: Optional[WalletProfile],
    snapshot: Optional[TokenSnapshot],
    modes: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any]
) -> Tuple[str, str]:
    """Extract the trading mode for a trade using dynamic selection.

    Priority:
    1. Explicit mode from trade.extra['mode'] if it exists in available modes
    2. Dynamic selection based on wallet median_hold_sec via select_mode()
    3. Fallback to 'U' or first available mode

    Args:
        trade: The trade event.
        wallet_profile: Wallet profile for dynamic mode selection.
        snapshot: Token snapshot for volatility-based aggressive triggers.
        modes: Available modes from config.
        cfg: Strategy configuration dict.

    Returns:
        Tuple of (mode_name: str, selection_reason: str).
    """
    # Step 1: Check for explicit mode in trade.extra (highest priority override)
    if trade.extra and isinstance(trade.extra, dict):
        explicit_mode = trade.extra.get("mode")
        if isinstance(explicit_mode, str) and explicit_mode.strip():
            mode_name = explicit_mode.strip()
            # Validate mode exists in config
            if mode_name in modes:
                return (mode_name, f"explicit_mode_override_{mode_name}")

    # Step 2: Use dynamic mode selection based on wallet behavior
    mode_name, selection_reason = select_mode(
        wallet_profile=wallet_profile,
        token_snapshot=snapshot,
        cfg=cfg
    )

    # Step 3: Validate selected mode exists in config
    if mode_name in modes:
        return (mode_name, selection_reason)

    # Step 4: Fallback - use 'U' if exists, otherwise first key
    if modes:
        fallback_mode = "U" if "U" in modes else next(iter(modes))
        return (fallback_mode, f"selected_mode_{mode_name}_not_found_fallback_{fallback_mode}")

    # No modes defined - use default 'U'
    return ("U", "no_modes_defined_default_U")
