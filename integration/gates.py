"""integration/gates.py

P0.1 gate checks driven by strategy/config/params_base.yaml.

Goals:
- Deterministic & tiny (no external API calls).
- "No missing" for token gates: requires a local TokenSnapshot cache (or inline fields).
- Returns structured reject reasons so we can aggregate why signals were not emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .trade_types import Trade
from .token_snapshot_store import TokenSnapshot
from .reject_reasons import (
    MISSING_SNAPSHOT,
    MIN_LIQUIDITY_FAIL,
    MIN_VOLUME_24H_FAIL,
    MAX_SPREAD_FAIL,
    TOP10_HOLDERS_FAIL,
    SINGLE_HOLDER_FAIL,
    HONEYPOT_FAIL,
    FREEZE_AUTHORITY_FAIL,
    MINT_AUTHORITY_FAIL,
    SECURITY_TOP_HOLDERS_FAIL,
    WALLET_MIN_ROI_FAIL,
    WALLET_MIN_WINRATE_FAIL,
    WALLET_MIN_TRADES_FAIL,
    SIMULATION_FAIL,
    HIGH_TAX_FAIL,
)

# Import simulation check from honeypot_filter
from strategy.honeypot_filter import check_simulation_security, is_honeypot_safe
from .reject_reasons import HONEYPOT_DETECTED


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    reasons: List[str]
    details: Dict[str, Any]

    @property
    def primary_reason(self) -> Optional[str]:
        return self.reasons[0] if self.reasons else None


def apply_gates(cfg: Dict[str, Any], trade: Trade, snapshot: Optional[TokenSnapshot]) -> GateDecision:
    reasons: List[str] = []
    details: Dict[str, Any] = {"mint": trade.mint, "tx_hash": trade.tx_hash}

    _token_gates(cfg=cfg, trade=trade, snapshot=snapshot, reasons=reasons, details=details)
    _security_gate(cfg=cfg, trade=trade, snapshot=snapshot, reasons=reasons, details=details)
    _simulation_gate(cfg=cfg, trade=trade, snapshot=snapshot, reasons=reasons, details=details)
    _honeypot_gate(cfg=cfg, trade=trade, snapshot=snapshot, reasons=reasons, details=details)
    _wallet_hard_filters(cfg=cfg, trade=trade, reasons=reasons, details=details)

    return GateDecision(passed=(len(reasons) == 0), reasons=reasons, details=details)


def _extract_security_data(snapshot: Optional[TokenSnapshot]) -> Tuple[bool, Optional[str]]:
    """Extract and validate security data from snapshot.extra["security"].

    Args:
        snapshot: TokenSnapshot containing security data in extra field

    Returns:
        Tuple of (is_safe, reason) where:
        - is_safe: True if all security checks pass
        - reason: Optional string explaining why the check failed
    """
    if snapshot is None or snapshot.extra is None:
        return True, None  # No snapshot, defer to other checks

    security = snapshot.extra.get("security")
    if security is None:
        return True, None  # No security data, defer to other checks

    # Check is_honeypot
    is_honeypot = security.get("is_honeypot")
    if is_honeypot is True:
        return False, HONEYPOT_FAIL

    # Check freeze_authority
    freeze_authority = security.get("freeze_authority")
    if freeze_authority is True:
        return False, FREEZE_AUTHORITY_FAIL

    # Check mint_authority
    mint_authority = security.get("mint_authority")
    if mint_authority is True:
        return False, MINT_AUTHORITY_FAIL

    # Check top_holders_pct (if present)
    top_holders_pct = security.get("top_holders_pct")
    if top_holders_pct is not None:
        try:
            pct = float(top_holders_pct)
            if pct > 50.0:  # Default threshold: reject if top holders own > 50%
                return False, SECURITY_TOP_HOLDERS_FAIL
        except (ValueError, TypeError):
            pass  # Invalid value, skip this check

    return True, None


def _token_gates(cfg: Dict[str, Any], trade: Trade, snapshot: Optional[TokenSnapshot], reasons: List[str], details: Dict[str, Any]) -> None:
    gates = (((cfg.get("token_profile") or {}).get("gates")) or {})

    # Require snapshot for token gates (P0.1)
    if snapshot is None:
        reasons.append(MISSING_SNAPSHOT)
        details["missing_snapshot_for_mint"] = trade.mint
        return

    # Pull values (snapshot preferred; fallback to inline trade fields if present)
    liq = snapshot.liquidity_usd if snapshot.liquidity_usd is not None else trade.liquidity_usd
    vol24 = snapshot.volume_24h_usd if snapshot.volume_24h_usd is not None else trade.volume_24h_usd
    spread = snapshot.spread_bps if snapshot.spread_bps is not None else trade.spread_bps
    top10 = snapshot.top10_holders_pct if snapshot.top10_holders_pct is not None else None
    single = snapshot.single_holder_pct if snapshot.single_holder_pct is not None else None

    min_liq = gates.get("min_liquidity_usd")
    if min_liq is not None:
        if liq is None:
            reasons.append(MISSING_SNAPSHOT)
            details["missing_field"] = "liquidity_usd"
        elif float(liq) < float(min_liq):
            reasons.append(MIN_LIQUIDITY_FAIL)
            details["liquidity_usd"] = float(liq)
            details["min_liquidity_usd"] = float(min_liq)

    min_vol = gates.get("min_volume_24h_usd")
    if min_vol is not None:
        if vol24 is None:
            reasons.append(MISSING_SNAPSHOT)
            details["missing_field"] = "volume_24h_usd"
        elif float(vol24) < float(min_vol):
            reasons.append(MIN_VOLUME_24H_FAIL)
            details["volume_24h_usd"] = float(vol24)
            details["min_volume_24h_usd"] = float(min_vol)

    max_spread = gates.get("max_spread_bps")
    if max_spread is not None:
        if spread is None:
            reasons.append(MISSING_SNAPSHOT)
            details["missing_field"] = "spread_bps"
        elif float(spread) > float(max_spread):
            reasons.append(MAX_SPREAD_FAIL)
            details["spread_bps"] = float(spread)
            details["max_spread_bps"] = float(max_spread)

    max_top10 = gates.get("max_top10_holders_pct")
    if max_top10 is not None and top10 is not None:
        if float(top10) > float(max_top10):
            reasons.append(TOP10_HOLDERS_FAIL)
            details["top10_holders_pct"] = float(top10)
            details["max_top10_holders_pct"] = float(max_top10)

    max_single = gates.get("max_single_holder_pct")
    if max_single is not None and single is not None:
        if float(single) > float(max_single):
            reasons.append(SINGLE_HOLDER_FAIL)
            details["single_holder_pct"] = float(single)
            details["max_single_holder_pct"] = float(max_single)


def _security_gate(cfg: Dict[str, Any], trade: Trade, snapshot: Optional[TokenSnapshot], reasons: List[str], details: Dict[str, Any]) -> None:
    """Check security data from snapshot.extra["security"].

    This gate validates:
    - is_honeypot: Reject if True
    - freeze_authority: Reject if True
    - mint_authority: Reject if True
    - top_holders_pct: Reject if > 50% (default threshold)
    """
    token_profile = cfg.get("token_profile") or {}
    security_config = token_profile.get("security") or {}
    enabled = bool(security_config.get("enabled", True))  # Default enabled
    if not enabled:
        return

    # Extract and validate security data from snapshot
    is_safe, reason = _extract_security_data(snapshot)

    if not is_safe and reason:
        reasons.append(reason)
        # Add security details to the output
        if snapshot and snapshot.extra and snapshot.extra.get("security"):
            security = snapshot.extra["security"]
            details["security"] = {
                "is_honeypot": security.get("is_honeypot"),
                "freeze_authority": security.get("freeze_authority"),
                "mint_authority": security.get("mint_authority"),
                "top_holders_pct": security.get("top_holders_pct"),
            }


def _simulation_gate(cfg: Dict[str, Any], trade: Trade, snapshot: Optional[TokenSnapshot], reasons: List[str], details: Dict[str, Any]) -> None:
    """Check simulation results from snapshot.extra["simulation"].

    This gate validates:
    - simulation.success: Reject if False
    - simulation.buy_tax_bps: Reject if exceeds threshold
    - simulation.sell_tax_bps: Reject if exceeds threshold
    """
    # Use the pure function from honeypot_filter
    is_safe, reason = check_simulation_security(snapshot, cfg)

    if not is_safe and reason:
        reasons.append(reason)
        # Add simulation details to the output
        if snapshot and snapshot.extra and snapshot.extra.get("simulation"):
            sim = snapshot.extra["simulation"]
            details["simulation"] = {
                "success": sim.get("success"),
                "error": sim.get("error"),
                "buy_tax_bps": sim.get("buy_tax_bps"),
                "sell_tax_bps": sim.get("sell_tax_bps"),
            }


def passes_honeypot_gate(snapshot: Optional[TokenSnapshot], cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """
    PR-K.3: Check if token passes honeypot safety gate.

    Args:
        snapshot: TokenSnapshot containing honeypot check data
        cfg: Runtime config with require_honeypot_safe setting

    Returns:
        Tuple of (passed: bool, reason: str)
    """
    # Check if honeypot gate is required
    security_cfg = (cfg.get("token_profile") or {}).get("security") or {}
    require_honeypot_safe = security_cfg.get("require_honeypot_safe", False)

    if not require_honeypot_safe:
        return True, "honeypot_check_skipped"

    # STRICT: require_honeypot_safe -> reject when snapshot/security data missing
    if snapshot is None:
        return False, HONEYPOT_DETECTED


    # Extract simulation data
    sim_success = True
    buy_tax_bps = None
    sell_tax_bps = None
    is_freezable = False
    snapshot_extra = None

    if snapshot is not None:
        snapshot_extra = snapshot.extra
        if snapshot_extra is not None:
            sim = snapshot_extra.get("simulation")
            if sim is not None:
                sim_success = sim.get("success", True)
                buy_tax_bps = sim.get("buy_tax_bps")
                sell_tax_bps = sim.get("sell_tax_bps")

            security = snapshot_extra.get("security")
            if security is not None:
                is_freezable = security.get("freeze_authority", False)

                # EARLY REJECT: explicit honeypot flag in snapshot.extra (matches honeypot_gate_smoke expectations)
                # Some fixtures mark honeypots via boolean flags instead of taxes; treat any explicit flag as unsafe.
                hp_flag = False
                # allow flags either at snapshot_extra level or inside snapshot_extra["security"]
                if snapshot_extra.get("honeypot") is True:
                    hp_flag = True
                if snapshot_extra.get("honeypot_detected") is True:
                    hp_flag = True
                if snapshot_extra.get("is_honeypot") is True:
                    hp_flag = True

                if security is not None:
                    if security.get("honeypot") is True:
                        hp_flag = True
                    if security.get("honeypot_detected") is True:
                        hp_flag = True
                    if security.get("is_honeypot") is True:
                        hp_flag = True
                    if security.get("scam") is True:
                        hp_flag = True

                if hp_flag:
                    return False, HONEYPOT_DETECTED

    # Use honeypot_filter to check safety
    is_safe = is_honeypot_safe(
        mint=snapshot.mint if snapshot else "",
        snapshot_extra=snapshot_extra,
        simulation_success=sim_success,
        buy_tax_bps=buy_tax_bps,
        sell_tax_bps=sell_tax_bps,
        is_freezable=is_freezable,
    )

    if is_safe:
        return True, "ok"
    else:
        return False, HONEYPOT_DETECTED


def _honeypot_gate(cfg: Dict[str, Any], trade: Trade, snapshot: Optional[TokenSnapshot], reasons: List[str], details: Dict[str, Any]) -> None:
    """PR-K.3: Honeypot safety gate integration.

    Validates token safety using honeypot_filter.is_honeypot_safe().
    Only active when config.require_honeypot_safe == true.
    """
    passed, reason = passes_honeypot_gate(snapshot, cfg)

    if not passed:
        reasons.append(reason)
        details["honeypot_gate"] = {"passed": False, "reason": reason}
    else:
        details["honeypot_gate"] = {"passed": True, "reason": reason}


def _wallet_hard_filters(cfg: Dict[str, Any], trade: Trade, reasons: List[str], details: Dict[str, Any]) -> None:
    hard = (((cfg.get("signals") or {}).get("hard_filters")) or {})

    min_wr = hard.get("min_wallet_winrate_30d")
    if min_wr is not None:
        if trade.wallet_winrate_30d is None:
            reasons.append(WALLET_MIN_WINRATE_FAIL)
            details["wallet_winrate_30d"] = None
            details["min_wallet_winrate_30d"] = float(min_wr)
        elif float(trade.wallet_winrate_30d) < float(min_wr):
            reasons.append(WALLET_MIN_WINRATE_FAIL)
            details["wallet_winrate_30d"] = float(trade.wallet_winrate_30d)
            details["min_wallet_winrate_30d"] = float(min_wr)

    min_roi = hard.get("min_wallet_roi_30d_pct")
    if min_roi is not None:
        if trade.wallet_roi_30d_pct is None:
            reasons.append(WALLET_MIN_ROI_FAIL)
            details["wallet_roi_30d_pct"] = None
            details["min_wallet_roi_30d_pct"] = float(min_roi)
        elif float(trade.wallet_roi_30d_pct) < float(min_roi):
            reasons.append(WALLET_MIN_ROI_FAIL)
            details["wallet_roi_30d_pct"] = float(trade.wallet_roi_30d_pct)
            details["min_wallet_roi_30d_pct"] = float(min_roi)

    min_tr = hard.get("min_wallet_trades_30d")
    if min_tr is not None:
        if trade.wallet_trades_30d is None:
            reasons.append(WALLET_MIN_TRADES_FAIL)
            details["wallet_trades_30d"] = None
            details["min_wallet_trades_30d"] = int(min_tr)
        elif int(trade.wallet_trades_30d) < int(min_tr):
            reasons.append(WALLET_MIN_TRADES_FAIL)
            details["wallet_trades_30d"] = int(trade.wallet_trades_30d)
            details["min_wallet_trades_30d"] = int(min_tr)
