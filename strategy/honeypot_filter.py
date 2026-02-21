"""
Honeypot Filter v2 - Token Security Evaluation

Pure logic for evaluating token safety before aggressive entry.
Analyzes simulation results or audit data (buy/sell tax, freeze authority)
to block tokens with high taxes or inability to sell (honeypot).

This is a critical component for passes_safety_filters().
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from integration.reject_reasons import HONEYPOT_FLAG, HONEYPOT_FREEZE, HONEYPOT_MINT_AUTH


# Rejection reason constants
REASON_SIM_FAIL = "sim_fail"
REASON_HIGH_TAX = "high_tax"
REASON_FREEZE_RISK = "freeze_risk"
REASON_UNKNOWN = "unknown"


@dataclass
class TokenSecurityData:
    """
    Data class representing token security information.
    Should be enriched from Ingestion layer.
    """
    symbol: str
    buy_tax_bps: Optional[int] = None
    sell_tax_bps: Optional[int] = None
    is_freezable: bool = False
    mint_authority: bool = False
    simulation_success: bool = True


@dataclass
class HoneypotFilterParams:
    """
    Configuration parameters for honeypot filter.
    All thresholds are configurable, not hardcoded.
    """
    max_tax_bps: int = 1000  # 10% max tax threshold
    block_freeze_authority: bool = True  # Block tokens with freeze authority
    allow_unknown: bool = False  # Allow tokens with missing tax data


def evaluate_security(
    data: TokenSecurityData,
    params: HoneypotFilterParams
) -> Tuple[bool, List[str]]:
    """
    Evaluate token security and return pass/fail verdict with reasons.
    
    Args:
        data: TokenSecurityData with enriched token information
        params: HoneypotFilterParams with configurable thresholds
    
    Returns:
        Tuple of (passed: bool, reject_reasons: List[str])
    """
    reasons: List[str] = []
    
    # Check 1: Simulation failure -> REJECT
    if not data.simulation_success:
        reasons.append(REASON_SIM_FAIL)
    
    # Check 2: Missing tax data -> REJECT if not allowed
    if data.buy_tax_bps is None or data.sell_tax_bps is None:
        if not params.allow_unknown:
            reasons.append(REASON_UNKNOWN)
    else:
        # Check 2: High tax -> REJECT
        # Check buy tax
        if data.buy_tax_bps > params.max_tax_bps:
            reasons.append(f"{REASON_HIGH_TAX}: buy_tax_bps={data.buy_tax_bps}")
        
        # Check sell tax
        if data.sell_tax_bps > params.max_tax_bps:
            reasons.append(f"{REASON_HIGH_TAX}: sell_tax_bps={data.sell_tax_bps}")
    
    # Check 3: Freeze authority risk -> REJECT
    if data.is_freezable and params.block_freeze_authority:
        reasons.append(REASON_FREEZE_RISK)
    
    # Return verdict
    passed = len(reasons) == 0
    return passed, reasons


def evaluate_security_dict(
    data: dict,
    params: dict
) -> Tuple[bool, List[str]]:
    """
    Convenience function to evaluate security from dict inputs.
    Useful for testing and integration.
    
    Args:
        data: Dict with token security fields
        params: Dict with filter parameters
    
    Returns:
        Tuple of (passed: bool, reject_reasons: List[str])
    """
    # Convert dict to TokenSecurityData
    token_data = TokenSecurityData(
        symbol=data.get("symbol", "UNKNOWN"),
        buy_tax_bps=data.get("buy_tax"),
        sell_tax_bps=data.get("sell_tax"),
        is_freezable=data.get("is_freezable", False),
        mint_authority=data.get("mint_authority", False),
        simulation_success=data.get("sim_ok", True)
    )
    
    # Convert dict to HoneypotFilterParams
    filter_params = HoneypotFilterParams(
        max_tax_bps=params.get("max_tax_bps", 1000),
        block_freeze_authority=params.get("block_freeze_authority", True),
        allow_unknown=params.get("allow_unknown", False)
    )
    
    return evaluate_security(token_data, filter_params)


# Alias for convenience
evaluate = evaluate_security


def check_security(
    snapshot: Optional[Any],
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Backward-compatible security gate used by signal_engine.

    Legacy smoke checks (PR-B.3) expect this function to:
    - respect token_profile.honeypot.enabled
    - reject missing snapshot/security payload when enabled
    - reject explicit honeypot/freeze/mint authority flags

    Returns:
        Tuple of (passed, reject_reason)
    """
    honeypot_cfg = ((cfg.get("token_profile") or {}).get("honeypot")) or {}
    if not bool(honeypot_cfg.get("enabled", False)):
        return True, None

    if snapshot is None or not hasattr(snapshot, "extra") or snapshot.extra is None:
        return True, None

    security = snapshot.extra.get("security")
    if security is None:
        return True, None

    if security.get("is_honeypot") is True:
        return False, HONEYPOT_FLAG

    if bool(honeypot_cfg.get("reject_if_freeze_authority_present", False)) and security.get("freeze_authority") is True:
        return False, HONEYPOT_FREEZE

    if bool(honeypot_cfg.get("reject_if_mint_authority_present", False)) and security.get("mint_authority") is True:
        return False, HONEYPOT_MINT_AUTH

    return True, None


def check_simulation_security(
    snapshot: Optional[Any],
    cfg: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    PR-K.3: Check simulation security from snapshot extra data.

    Args:
        snapshot: TokenSnapshot or dict with security/simulation data
        cfg: Runtime config with security thresholds

    Returns:
        Tuple of (passed: bool, reason: Optional[str])
    """
    if snapshot is None:
        return True, None

    # Handle TokenSnapshot object
    snapshot_extra = None
    if hasattr(snapshot, 'extra'):
        snapshot_extra = snapshot.extra
    elif isinstance(snapshot, dict):
        snapshot_extra = snapshot
    else:
        return True, None

    if snapshot_extra is None:
        return True, None

    sim = snapshot_extra.get("simulation")
    if sim is None:
        return True, None

    sim_success = sim.get("success", True)
    if not sim_success:
        return False, "simulation_failed"

    buy_tax = sim.get("buy_tax_bps")
    sell_tax = sim.get("sell_tax_bps")

    security_cfg = (cfg.get("token_profile") or {}).get("security") or {}
    max_tax = security_cfg.get("max_tax_bps", 1000)

    if buy_tax is not None and buy_tax > max_tax:
        return False, f"high_buy_tax: {buy_tax}bps"

    if sell_tax is not None and sell_tax > max_tax:
        return False, f"high_sell_tax: {sell_tax}bps"

    return True, None


def is_honeypot_safe(
    mint: str,
    snapshot_extra: Optional[Dict[str, Any]] = None,
    simulation_success: bool = True,
    buy_tax_bps: Optional[int] = None,
    sell_tax_bps: Optional[int] = None,
    is_freezable: bool = False,
) -> bool:
    """
    Determine if a token is honeypot-safe based on available data.

    This function combines data from:
    - Token snapshot extra fields (security.is_honeypot)
    - Simulation results (buy_tax_bps, sell_tax_bps, success)
    - Token properties (is_freezable)

    Args:
        mint: Token mint address
        snapshot_extra: Optional dict with security/simulation data from snapshot
        simulation_success: Whether the dry-run simulation succeeded
        buy_tax_bps: Buy tax in basis points
        sell_tax_bps: Sell tax in basis points
        is_freezable: Whether the token has freeze authority

    Returns:
        True if token is honeypot-safe, False otherwise
    """
    # Check snapshot security data first
    if snapshot_extra is not None:
        security = snapshot_extra.get("security")
        if security is not None:
            # Direct honeypot flag
            is_honeypot = security.get("is_honeypot")
            if is_honeypot is True:
                return False

    # Check simulation success
    if not simulation_success:
        return False

    # Check tax thresholds (default 10% = 1000 bps)
    if buy_tax_bps is not None and buy_tax_bps > 1000:
        return False
    if sell_tax_bps is not None and sell_tax_bps > 1000:
        return False

    # Check freeze authority
    if is_freezable:
        return False

    return True


if __name__ == "__main__":
    # Quick self-test
    print("Honeypot Filter v2 Self-Test")
    print("=" * 40)
    
    # Test cases
    test_cases = [
        ("SOL_GOOD", {"buy_tax": 0, "sell_tax": 0, "is_freezable": False, "sim_ok": True}),
        ("SCAM_TAX", {"buy_tax": 5000, "sell_tax": 10000, "is_freezable": False, "sim_ok": True}),
        ("SCAM_HONEY", {"buy_tax": 0, "sell_tax": 0, "is_freezable": False, "sim_ok": False}),
        ("SCAM_FREEZE", {"buy_tax": 0, "sell_tax": 0, "is_freezable": True, "sim_ok": True}),
    ]
    
    params = HoneypotFilterParams(
        max_tax_bps=1000,
        block_freeze_authority=True,
        allow_unknown=False
    )
    
    for symbol, data in test_cases:
        data["symbol"] = symbol
        passed, reasons = evaluate_security_dict(data, params)
        status = "PASS" if passed else "REJECT"
        print(f"{symbol}: {status} - {reasons}")
