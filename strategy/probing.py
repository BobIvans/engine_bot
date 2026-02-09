"""strategy/probing.py

PR-K.2 Probe Trade Logic - Pure Decision Logic.

This module contains pure functions for evaluating whether a trade should be
executed as a "probe" (small test trade) for unverified tokens.

Pure function: no I/O, reads from config and snapshot.extra, returns structured result.

Configuration:
    token_profile.honeypot.probe_trade.enabled: bool
    token_profile.honeypot.probe_trade.max_probe_cost_usd: float

Probe state in snapshot.extra:
    snapshot.extra["probe_state"]["passed"]: bool
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from integration.token_snapshot_store import TokenSnapshot


@dataclass(frozen=True)
class ProbeResult:
    """Result of probe trade evaluation.
    
    Attributes:
        is_probe: True if this should be executed as a probe trade.
        size_usd: Suggested position size (capped for probe trades).
        reason: Human-readable reason for the decision.
    """
    is_probe: bool
    size_usd: float
    reason: str


def evaluate_probe(
    snapshot: Optional[TokenSnapshot],
    trade_size_usd: float,
    cfg: Dict[str, Any],
) -> ProbeResult:
    """Evaluate whether a trade should be executed as a probe.
    
    This is a pure function that:
    1. Checks if probe trading is enabled in config
    2. Checks if the token has already been verified (probe_passed)
    3. Returns probe result with capped size if needed
    
    Args:
        snapshot: TokenSnapshot containing probe_state in extra["probe_state"]
        trade_size_usd: Original intended trade size in USD
        cfg: Strategy configuration dict with probe_trade settings
        
    Returns:
        ProbeResult with is_probe flag, suggested size, and reason.
    """
    # Step 1: Get probe config
    probe_cfg = cfg.get("token_profile", {}).get("honeypot", {}).get("probe_trade", {})
    enabled = probe_cfg.get("enabled", False)
    
    if not enabled:
        return ProbeResult(
            is_probe=False,
            size_usd=trade_size_usd,
            reason="probe_disabled",
        )
    
    # Step 2: Check if we have snapshot data
    if snapshot is None or snapshot.extra is None:
        # No snapshot - force probe mode for safety
        max_probe_size = probe_cfg.get("max_probe_cost_usd", 10.0)
        return ProbeResult(
            is_probe=True,
            size_usd=min(trade_size_usd, max_probe_size),
            reason="no_snapshot_data_force_probe",
        )
    
    # Step 3: Check probe_state in snapshot.extra
    probe_state = snapshot.extra.get("probe_state")
    if probe_state is None:
        # No probe state - force probe mode
        max_probe_size = probe_cfg.get("max_probe_cost_usd", 10.0)
        return ProbeResult(
            is_probe=True,
            size_usd=min(trade_size_usd, max_probe_size),
            reason="no_probe_state_force_probe",
        )
    
    # Step 4: Check if probe has passed
    probe_passed = probe_state.get("passed")
    if probe_passed is True:
        return ProbeResult(
            is_probe=False,
            size_usd=trade_size_usd,
            reason="probe_already_passed",
        )
    
    # Step 5: Token not verified - execute as probe with capped size
    max_probe_size = probe_cfg.get("max_probe_cost_usd", 10.0)
    return ProbeResult(
        is_probe=True,
        size_usd=min(trade_size_usd, max_probe_size),
        reason="token_not_verified_probe_required",
    )


def evaluate_probe_from_dict(
    probe_data: Optional[Dict[str, Any]],
    trade_size_usd: float,
    cfg: Dict[str, Any],
) -> ProbeResult:
    """Convenience function for evaluating probe from dict data (for testing).
    
    Args:
        probe_data: Dictionary containing probe_state, or None
        trade_size_usd: Original intended trade size in USD
        cfg: Strategy configuration dict
        
    Returns:
        ProbeResult with is_probe flag, suggested size, and reason.
    """
    # Step 1: Get probe config
    probe_cfg = cfg.get("token_profile", {}).get("honeypot", {}).get("probe_trade", {})
    enabled = probe_cfg.get("enabled", False)
    
    if not enabled:
        return ProbeResult(
            is_probe=False,
            size_usd=trade_size_usd,
            reason="probe_disabled",
        )
    
    # Step 2: Check probe data
    if probe_data is None:
        max_probe_size = probe_cfg.get("max_probe_cost_usd", 10.0)
        return ProbeResult(
            is_probe=True,
            size_usd=min(trade_size_usd, max_probe_size),
            reason="no_probe_data_force_probe",
        )
    
    # Step 3: Check if probe has passed
    probe_passed = probe_data.get("passed")
    if probe_passed is True:
        return ProbeResult(
            is_probe=False,
            size_usd=trade_size_usd,
            reason="probe_already_passed",
        )
    
    # Step 4: Token not verified - execute as probe with capped size
    max_probe_size = probe_cfg.get("max_probe_cost_usd", 10.0)
    return ProbeResult(
        is_probe=True,
        size_usd=min(trade_size_usd, max_probe_size),
        reason="token_not_verified_probe_required",
    )
