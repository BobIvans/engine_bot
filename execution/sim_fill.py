"""execution/sim_fill.py

P0 execution fill simulator.
Handles fills, partial exits, and SL updates.

Deterministic knobs:
- latency sampled from execution.latency_model
- slippage estimated from either constant_bps or liquidity heuristic
- TTL can expire
- Dynamic TTL and slippage based on volatility (PR-E.3)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

from integration.token_snapshot_store import TokenSnapshot
from execution.latency_model import LogNormalLatencyParams, sample_lognormal_ms
from execution.transaction_builder import calculate_swap_amount, is_dust_remaining
from strategy.dynamic_adjustment import calculate_dynamic_ttl, calculate_slippage_bps
from strategy.trade_types import ExitSignal, ExitType, SimulatedTrade


@dataclass(frozen=True)
class FillResult:
    status: str  # filled | partial | none
    fill_price: Optional[float]
    slippage_bps: Optional[float]
    slippage_bps: Optional[float]
    latency_ms: int
    ttl_expired: bool
    partial_fill_retry_attempts: int = 0  # PR-Z.2: Tracker for parity with live


@dataclass(frozen=True)
class ExitResult:
    """Result of processing an exit signal."""
    trade: SimulatedTrade
    amount_sold: float
    pnl_realized: float
    is_closed: bool
    message: str


def simulate_fill(
    *,
    side: str,
    mid_price: float,
    size_usd: float,
    snapshot: Optional[TokenSnapshot],
    execution_cfg: Dict[str, Any],
    mode_ttl_sec: Optional[int],
    seed: Optional[int],
    vol_30s: float = 0.0,  # PR-E.3: volatility input
) -> FillResult:
    latency_cfg = (execution_cfg.get("latency") or {})
    enabled = bool(latency_cfg.get("enabled", True))
    latency_ms = 0
    if enabled:
        obs = latency_cfg.get("observe_delay_ms") or {}
        params = LogNormalLatencyParams(
            mean_ms=float(obs.get("mean", 250)),
            sigma=float(obs.get("sigma", 0.4)),
            clamp_min_ms=int(obs.get("clamp_min", 80)),
            clamp_max_ms=int(obs.get("clamp_max", 900)),
        )
        latency_ms = sample_lognormal_ms(params, seed=seed)

    # PR-E.3: Dynamic TTL calculation
    ttl_cfg = (execution_cfg.get("orders") or {}).get("ttl") or {}
    default_ttl_sec = int(ttl_cfg.get("default_ttl_sec", 120))
    default_ttl_ms = default_ttl_sec * 1000

    # Use dynamic TTL if enabled in config
    effective_ttl_ms = calculate_dynamic_ttl(default_ttl_ms, vol_30s, execution_cfg)

    # Convert to seconds for comparison with latency
    effective_ttl_sec = effective_ttl_ms / 1000.0
    ttl_expired = (latency_ms / 1000.0) > effective_ttl_sec
    if ttl_expired:
        return FillResult(status="none", fill_price=None, slippage_bps=None, latency_ms=latency_ms, ttl_expired=True)

    slip_cfg = (execution_cfg.get("slippage_model") or {})
    model = slip_cfg.get("model", "constant_bps")
    constant_bps = float(slip_cfg.get("constant_bps", 80))
    impact_cap = float(slip_cfg.get("impact_cap_bps", 200))

    slippage_bps = constant_bps

    # PR-E.3: Dynamic slippage calculation
    dynamic_cfg = execution_cfg.get("dynamic_execution", {})
    if dynamic_cfg.get("enabled", False):
        liq_usd = float(snapshot.liquidity_usd) if snapshot and snapshot.liquidity_usd else 0.0
        slippage_bps = calculate_slippage_bps(constant_bps, size_usd, liq_usd, vol_30s, execution_cfg)
    elif model == "amm_xyk" and snapshot is not None and snapshot.liquidity_usd:
        ratio = max(size_usd, 0.0) / max(float(snapshot.liquidity_usd), 1.0)
        slippage_bps = min(impact_cap, ratio * impact_cap)

    fill_cfg = (execution_cfg.get("fill_model") or {})
    base_fill_rate = float(fill_cfg.get("base_fill_rate", 0.80))
    p = base_fill_rate
    p -= float(fill_cfg.get("penalty_per_1000ms_latency", 0.03)) * (latency_ms / 1000.0)
    p = max(min(p, 0.99), 0.01)

    # deterministic "coin flip" based on seed
    h = 0 if seed is None else int(seed) & 0xFFFFFFFF
    u = (h % 10_000) / 10_000.0
    if u > p:
        return FillResult(status="none", fill_price=None, slippage_bps=slippage_bps, latency_ms=latency_ms, ttl_expired=False)

    sign = 1.0 if side.upper() == "BUY" else -1.0
    fill_price = float(mid_price) * (1.0 + sign * (slippage_bps / 10_000.0))
    return FillResult(status="filled", fill_price=fill_price, slippage_bps=slippage_bps, latency_ms=latency_ms, ttl_expired=False)


def process_exit_signal(
    trade: SimulatedTrade,
    signal: ExitSignal,
    current_price: float,
) -> ExitResult:
    """Process an exit signal against a simulated trade.

    Handles partial exits, full exits, and SL updates.

    Args:
        trade: The simulated trade to process exit for.
        signal: ExitSignal defining what to do.
        current_price: Current market price.

    Returns:
        ExitResult with updated trade state.
    """
    # Calculate amount to sell based on size_pct
    amount_to_sell = int(trade.size_remaining * signal.size_pct)

    # Ensure at least 1 token
    if amount_to_sell < 1:
        amount_to_sell = 1

    # Don't exceed remaining balance
    if amount_to_sell > trade.size_remaining:
        amount_to_sell = int(trade.size_remaining)

    # Calculate realized PnL
    pnl_realized = (current_price - trade.entry_price) * amount_to_sell

    # Update trade state
    new_size = trade.size_remaining - amount_to_sell

    # Check if trade should be closed
    is_closed = is_dust_remaining(new_size) or signal.size_pct >= 1.0

    if is_closed:
        new_status = "CLOSED"
        new_size = 0.0
        message = "Full Exit - Trade Closed"
    else:
        new_status = "OPEN"
        message = "Partial Fill - Position Still Open"

    # Handle TRAILING_STOP_UPDATE
    new_trail_stop = trade.trail_stop_price
    new_trail_activation = trade.trail_activation_price
    if signal.exit_type == ExitType.TRAILING_STOP_UPDATE and signal.trail_stop_pct is not None:
        new_trail_stop = current_price * (1.0 - signal.trail_stop_pct)
        if signal.trail_activation_pct is not None:
            new_trail_activation = current_price * (1.0 + signal.trail_activation_pct)
        message = "Trailing Stop Updated"

    # Create updated trade
    updated_trade = SimulatedTrade(
        wallet=trade.wallet,
        mint=trade.mint,
        entry_price=trade.entry_price,
        size_remaining=new_size,
        size_initial=trade.size_initial,
        realized_pnl=trade.realized_pnl + pnl_realized,
        status=new_status,
        trail_stop_price=new_trail_stop,
        trail_activation_price=new_trail_activation,
    )

    print(f"[sim_fill] {message}: sold={amount_to_sell}, pnl={pnl_realized:.2f}, remaining={new_size}", file=sys.stderr)

    return ExitResult(
        trade=updated_trade,
        amount_sold=amount_to_sell,
        pnl_realized=pnl_realized,
        is_closed=is_closed,
        message=message,
    )
