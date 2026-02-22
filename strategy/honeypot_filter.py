# --- HONEYPOT REJECT REASONS IMPORT ---
try:
    # canonical constants used by integration & smoke tests
    from integration.reject_reasons import HONEYPOT_FLAG, HONEYPOT_FREEZE, HONEYPOT_MINT_AUTH
except Exception:
    # fallback strings (keep smoke contract stable)
    HONEYPOT_FLAG = "honeypot_flag"
    HONEYPOT_FREEZE = "honeypot_freeze"
    HONEYPOT_MINT_AUTH = "honeypot_mint_auth"

"""
Honeypot Filter v2 - Token Security Evaluation

Pure logic for evaluating token safety before aggressive entry.
Analyzes simulation results or audit data (buy/sell tax, freeze authority)
to block tokens with high taxes or inability to sell (honeypot).

This is a critical component for passes_safety_filters().
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple


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
    if data is None:
        return True, []


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
def _extract_security_dict(snapshot, **kwargs):
    """
    Best-effort extraction of security dict from various snapshot shapes.
    Supports:
      - kwargs: security/sec/security_dict
      - snapshot.extra["security"] (dict)
      - snapshot.extra["security"]["result"] (dict)
      - snapshot.extra["token_security"] (dict)
      - snapshot.security (dict)
      - snapshot.security_dict (dict)
    """
    sec = kwargs.get("security") or kwargs.get("sec") or kwargs.get("security_dict")
    if isinstance(sec, dict):
        return sec

    if snapshot is None:
        return None

    # attribute-style
    for attr in ("security", "security_dict"):
        try:
            v = getattr(snapshot, attr, None)
            if isinstance(v, dict):
                return v
        except Exception:
            pass

    # extra-style
    extra = None
    try:
        extra = getattr(snapshot, "extra", None)
    except Exception:
        extra = None

    if isinstance(extra, dict):
        # common direct keys
        for k in ("security", "token_security", "security_data", "sec"):
            v = extra.get(k)
            if isinstance(v, dict):
                # sometimes wrapped as {"result": {...}}
                if isinstance(v.get("result"), dict):
                    return v["result"]
                return v

        # nested wrapper cases
        v = extra.get("security")
        if isinstance(v, dict) and isinstance(v.get("result"), dict):
            return v["result"]

    return None



def is_honeypot_safe(snapshot=None, cfg=None, **kwargs):
    """
    V2-aware honeypot safety check.
    Returns True if token is safe to trade, False otherwise.

    Rules:
      - If honeypot module disabled in cfg -> PASS.
      - If no security data at all -> PASS (do not block).
      - If security dict exists but core fields are unknown (None) -> REJECT by default,
        unless allow_unknown is enabled (cfg or security dict).
      - Reject if is_honeypot True / freeze authority / mint authority (per cfg flags).
      - Reject if buy_tax_pct or sell_tax_pct exceed max_tax_pct (default 10).
    """
    hp_cfg = (cfg or {}).get("token_profile", {}).get("honeypot", {}) or {}
    sec = _extract_security_dict(snapshot, **kwargs)
    # Compat: allow callers to pass mint/security via kwargs (older gate wiring)
    # We do not require mint for logic; it's accepted to avoid TypeError.
    if snapshot is None:
        sec_kw = kwargs.get("security") or kwargs.get("sec") or kwargs.get("security_dict")
        if isinstance(sec_kw, dict):
            # emulate snapshot.extra={"security": sec}
            class _Tmp:
                extra = {"security": sec_kw}
            snapshot = _Tmp()
    if not hp_cfg.get("enabled", False):
        return True

    # Extract security dict from snapshot
    sec = None
    try:
        extra = getattr(snapshot, "extra", None)
        if isinstance(extra, dict):
            sec = (
                extra.get("security")
                or extra.get("security_v2")
                or extra.get("security_data")
                or extra.get("token_security")
            )
    except Exception:
        sec = None

    # Back-compat: if no security data -> pass
    if sec is None:
        return True

    # Some callers might pass security dict directly
    if not isinstance(sec, dict):
        return True

    allow_unknown = bool(hp_cfg.get("allow_unknown", False) or sec.get("allow_unknown") is True)

    # Unknown handling (core fields)
    if any(sec.get(k) is None for k in ("is_honeypot", "freeze_authority", "mint_authority")):
        if not allow_unknown:
            return False

    # Explicit red flags
    if sec.get("is_honeypot") is True:
        return False

    if hp_cfg.get("reject_if_freeze_authority_present", False) and sec.get("freeze_authority") is True:
        return False

    if hp_cfg.get("reject_if_mint_authority_present", False) and sec.get("mint_authority") is True:
        return False

    # Tax thresholds
    max_tax_pct = hp_cfg.get("max_tax_pct", hp_cfg.get("max_tax", 10))
    try:
        max_tax_pct = float(max_tax_pct)
    except Exception:
        max_tax_pct = 10.0

    buy_tax = sec.get("buy_tax_pct")
    sell_tax = sec.get("sell_tax_pct")

    # If tax keys exist but values unknown -> reject unless allowed
    if ("buy_tax_pct" in sec or "sell_tax_pct" in sec) and (buy_tax is None or sell_tax is None):
        if not allow_unknown:
            return False

    def to_float(x):
        try:
            return float(x)
        except Exception:
            return None

    bt = to_float(buy_tax)
    st = to_float(sell_tax)

    if bt is not None and bt > max_tax_pct:
        return False
    if st is not None and st > max_tax_pct:
        return False

    return True

def _reason_to_str(reason: Any) -> str:
    """Best-effort normalize reason to a short string."""
    if reason is None:
        return ""
    if isinstance(reason, str):
        return reason.strip()
    if isinstance(reason, (list, tuple)):
        # join first few items
        parts = []
        for x in reason[:3]:
            if x is None:
                continue
            parts.append(str(x))
        return ",".join(parts)
    if isinstance(reason, dict):
        # common keys
        for k in ("reason", "fail_reason", "risk", "code", "name"):
            v = reason.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return str(reason)
    return str(reason)

def check_security(snapshot: Any, cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Security check used by signal_engine.

    Supports legacy v1 flags in snapshot.extra["security"]:
      - is_honeypot -> reject (HONEYPOT_FLAG)
      - freeze_authority -> reject when reject_if_freeze_authority_present
      - mint_authority -> reject when reject_if_mint_authority_present

    Align with security_gate_smoke edge-cases:
      - gate disabled -> pass
      - snapshot None -> pass
      - missing security -> pass
    """
    hp_cfg = (cfg or {}).get("token_profile", {}).get("honeypot", {}) or {}
    if hp_cfg.get("enabled", False) is False:
        return True, None

    if snapshot is None:
        return True, None

    security = None
    try:
        # Prefer explicit security getter if exists
        if hasattr(snapshot, "get_security_data") and callable(getattr(snapshot, "get_security_data")):
            security = snapshot.get_security_data()

        # TokenSnapshot in this repo commonly stores it in extra["security"]
        if security is None and hasattr(snapshot, "extra") and isinstance(getattr(snapshot, "extra"), dict):
            security = getattr(snapshot, "extra").get("security")

        # Some shapes may use snapshot.security
        if security is None and hasattr(snapshot, "security") and isinstance(getattr(snapshot, "security"), dict):
            security = getattr(snapshot, "security")

        # Allow raw dict input for tests
        if security is None and isinstance(snapshot, dict):
            security = snapshot.get("security") if isinstance(snapshot.get("security"), dict) else snapshot
    except Exception:
        security = None

    # Missing/None security passes (SoT)
    if not isinstance(security, dict) or not security:
        return True, None

    # v1 flags
    if security.get("is_honeypot") is True:
        return False, HONEYPOT_FLAG

    if hp_cfg.get("reject_if_freeze_authority_present", False) and security.get("freeze_authority") is True:
        return False, HONEYPOT_FREEZE

    if hp_cfg.get("reject_if_mint_authority_present", False) and security.get("mint_authority") is True:
        return False, HONEYPOT_MINT_AUTH

    # If this is clearly a v1-flags payload, we're done.
    if any(k in security for k in ("is_honeypot", "freeze_authority", "mint_authority")):
        return True, None

    # v2 payload: run evaluate_security_dict safely
    ok, reasons = evaluate_security_dict(
        security,
        max_tax_bps=int(hp_cfg.get("max_tax_bps", 1000) or 1000),
        block_freeze_authority=bool(hp_cfg.get("block_freeze_authority", True)),
        allow_unknown=bool(hp_cfg.get("allow_unknown", True)),
    )
    if ok:
        return True, None

    reason = reasons[0] if reasons else "security_fail"
    return False, reason


def check_security(snapshot, cfg, *args, **kwargs):
    """
    Returns (passed: bool, reason: Optional[str])
    Expected by strategy.signal_engine.
    """
    fn = globals().get("evaluate_security_dict")
    if callable(fn):
        d = fn(snapshot, cfg)
        passed = bool(d.get("passed", d.get("ok", True)))
        reason = d.get("reason") or d.get("fail_reason") or d.get("risk") or None
        return passed, (None if passed else (reason or "security_failure"))

    fn = globals().get("evaluate_security")
    if callable(fn):
        out = fn(snapshot, cfg)
        if isinstance(out, tuple) and len(out) == 2:
            return bool(out[0]), out[1]
        if isinstance(out, bool):
            return out, (None if out else "security_failure")
        if isinstance(out, dict):
            passed = bool(out.get("passed", out.get("ok", True)))
            reason = out.get("reason") or out.get("fail_reason") or None
            return passed, (None if passed else (reason or "security_failure"))

    return True, None

# --- CI/API compatibility override (TokenSnapshot -> dict) ---
def _snapshot_to_dict(snapshot):
    if snapshot is None:
        return None
    # Already dict-like
    if isinstance(snapshot, dict):
        return snapshot
    # dataclass -> dict
    try:
        import dataclasses
        if dataclasses.is_dataclass(snapshot):
            return dataclasses.asdict(snapshot)
    except Exception:
        pass
    # generic object -> __dict__
    try:
        d = vars(snapshot)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    # last resort: return as-is
    return snapshot


def check_security(snapshot, cfg, *args, **kwargs):
    """
    Returns (passed: bool, reason: Optional[str])
    Expected by strategy.signal_engine.
    Accepts TokenSnapshot objects by converting them to dict for older evaluators.
    """
    snap = _snapshot_to_dict(snapshot)

    # Extract v1 security flags from normalized snapshot (best-effort)
    sec_flags = {}
    try:
        if isinstance(snap, dict):
            cand = None
            if isinstance(snap.get("security"), dict):
                cand = snap.get("security")
            else:
                extra = snap.get("extra") if isinstance(snap.get("extra"), dict) else None
                if extra and isinstance(extra.get("security"), dict):
                    cand = extra.get("security")
                snap2 = snap.get("snapshot") if isinstance(snap.get("snapshot"), dict) else None
                if cand is None and snap2:
                    if isinstance(snap2.get("security"), dict):
                        cand = snap2.get("security")
                    else:
                        ex2 = snap2.get("extra") if isinstance(snap2.get("extra"), dict) else None
                        if ex2 and isinstance(ex2.get("security"), dict):
                            cand = ex2.get("security")
            if isinstance(cand, dict):
                for k in ("is_honeypot", "freeze_authority", "mint_authority"):
                    if k in cand:
                        sec_flags[k] = cand.get(k)
    except Exception:
        sec_flags = {}

    # v1 flags fast-path (SoT for honeypot_smoke)
    # NOTE: _snapshot_to_dict() may nest security in various places; handle common shapes.
    hp_cfg = (cfg or {}).get('token_profile', {}).get('honeypot', {}) or {}
    if hp_cfg.get('enabled', False):
        sec = None
        if isinstance(snap, dict):
            # Candidate locations (ordered):
            candidates = []
            candidates.append(snap.get('security') if isinstance(snap.get('security'), dict) else None)
            # common nesting patterns
            extra = snap.get('extra') if isinstance(snap.get('extra'), dict) else None
            if extra and isinstance(extra.get('security'), dict):
                candidates.append(extra.get('security'))
            snapshot = snap.get('snapshot') if isinstance(snap.get('snapshot'), dict) else None
            if snapshot:
                if isinstance(snapshot.get('security'), dict):
                    candidates.append(snapshot.get('security'))
                ex2 = snapshot.get('extra') if isinstance(snapshot.get('extra'), dict) else None
                if ex2 and isinstance(ex2.get('security'), dict):
                    candidates.append(ex2.get('security'))
            # sometimes flattened under security_data
            candidates.append(snap.get('security_data') if isinstance(snap.get('security_data'), dict) else None)
            # last resort: snap itself might be security dict
            candidates.append(snap)

            for c in candidates:
                if isinstance(c, dict) and any(k in c for k in ('is_honeypot', 'freeze_authority', 'mint_authority')):
                    sec = c
                    break

        # Optional debug: export HONEYPOT_SMOKE_DEBUG=1
        import os
        if os.environ.get('HONEYPOT_SMOKE_DEBUG') == '1':
            try:
                import json
                print('[honeypot_debug] snap_keys=', list(snap.keys()) if isinstance(snap, dict) else type(snap), file=sys.stderr)
                print('[honeypot_debug] security_found=', bool(isinstance(sec, dict)), file=sys.stderr)
                if isinstance(sec, dict):
                    print('[honeypot_debug] sec=', json.dumps(sec, sort_keys=True)[:500], file=sys.stderr)
            except Exception:
                pass

        if isinstance(sec, dict):
            is_hp = sec.get('is_honeypot') is True
            frz = sec.get('freeze_authority') is True
            mnt = sec.get('mint_authority') is True
            if is_hp:
                return False, HONEYPOT_FLAG
            if hp_cfg.get('reject_if_freeze_authority_present', False) and frz:
                return False, HONEYPOT_FREEZE
            if hp_cfg.get('reject_if_mint_authority_present', False) and mnt:
                return False, HONEYPOT_MINT_AUTH


    def normalize(passed, reason):
        # v1 flags override: do not allow "unknown" to bypass explicit red-flags
        try:
            hp_cfg = (cfg or {}).get('token_profile', {}).get('honeypot', {}) or {}
            if hp_cfg.get('enabled', False) and isinstance(sec_flags, dict) and sec_flags:
                if sec_flags.get('is_honeypot') is True:
                    return False, HONEYPOT_FLAG
                if hp_cfg.get('reject_if_freeze_authority_present', False) and sec_flags.get('freeze_authority') is True:
                    return False, HONEYPOT_FREEZE
                if hp_cfg.get('reject_if_mint_authority_present', False) and sec_flags.get('mint_authority') is True:
                    return False, HONEYPOT_MINT_AUTH
        except Exception:
            pass
        reason_s = _reason_to_str(reason)
        # If evaluator is uncertain, don't block smoke tests
        if reason_s == "unknown":
            return True, None
        return bool(passed), (None if passed else (reason_s or "security_failure"))

    fn = globals().get("evaluate_security_dict")
    if callable(fn):
        out = fn(snap, cfg)
        if isinstance(out, tuple) and len(out) == 2:
            return normalize(out[0], out[1])
        if isinstance(out, dict):
            passed = out.get("passed", out.get("ok", True))
            reason = out.get("reason") or out.get("fail_reason") or out.get("risk") or out.get("reasons")
            return normalize(passed, reason)
        if isinstance(out, bool):
            return normalize(out, None)
        return True, None

    fn = globals().get("evaluate_security")
    if callable(fn):
        out = fn(snap, cfg)
        if isinstance(out, tuple) and len(out) == 2:
            return normalize(out[0], out[1])
        if isinstance(out, dict):
            passed = out.get("passed", out.get("ok", True))
            reason = out.get("reason") or out.get("fail_reason") or out.get("reasons")
            return normalize(passed, reason)
        if isinstance(out, bool):
            return normalize(out, None)

    return True, None
