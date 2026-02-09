"""Deterministic wallet tiering.

This module intentionally has **no** external dependencies.
It provides a small, stable contract used by integration.paper_pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


# Default thresholds are deliberately conservative and stable.
# Config may override these by providing:
#   wallet_tiers:
#     tier0: {roi_30d_pct_min: 50, winrate_30d_min: 0.70, trades_30d_min: 200}
#     tier1: {roi_30d_pct_min: 20, winrate_30d_min: 0.60, trades_30d_min: 50}
#     tier2: {roi_30d_pct_min: 10, trades_30d_min: 10}
DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "tier0": {
        "roi_30d_pct_min": 50.0,
        "winrate_30d_min": 0.70,
        "trades_30d_min": 200.0,
    },
    "tier1": {
        "roi_30d_pct_min": 20.0,
        "winrate_30d_min": 0.60,
        "trades_30d_min": 50.0,
    },
    "tier2": {
        "roi_30d_pct_min": 10.0,
        "trades_30d_min": 10.0,
    },
}


def tier_thresholds(cfg: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    """Return thresholds for tiering.

    If config doesn't provide overrides, defaults are returned.
    """

    out: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    wt = cfg.get("wallet_tiers") if isinstance(cfg, Mapping) else None
    if isinstance(wt, Mapping):
        for tier_name, params in wt.items():
            if not isinstance(tier_name, str) or not isinstance(params, Mapping):
                continue
            if tier_name not in out:
                out[tier_name] = {}
            for k, v in params.items():
                if not isinstance(k, str):
                    continue
                try:
                    out[tier_name][k] = float(v)
                except Exception:
                    # Ignore invalid override values.
                    continue
    return out


def _get_float(profile: Any, key: str) -> Optional[float]:
    if profile is None:
        return None
    # Mapping path
    if isinstance(profile, Mapping) and key in profile:
        try:
            v = profile.get(key)
            return None if v is None else float(v)
        except Exception:
            return None
    # Attribute path
    if hasattr(profile, key):
        try:
            v = getattr(profile, key)
            return None if v is None else float(v)
        except Exception:
            return None
    return None


def resolve_tier(wallet_profile: Any, cfg: Mapping[str, Any]) -> str:
    """Resolve a tier label for a given wallet profile.

    Returns one of: "tier0", "tier1", "tier2", "tier3".

    Missing or invalid fields fall back to "tier3".
    """

    roi = _get_float(wallet_profile, "roi_30d_pct")
    win = _get_float(wallet_profile, "winrate_30d")
    trades = _get_float(wallet_profile, "trades_30d")

    if roi is None or trades is None:
        return "tier3"

    th = tier_thresholds(cfg)

    # tier0 (optional)
    t0 = th.get("tier0") or {}
    if (
        roi >= float(t0.get("roi_30d_pct_min", DEFAULT_THRESHOLDS["tier0"]["roi_30d_pct_min"]))
        and (win is not None)
        and win >= float(t0.get("winrate_30d_min", DEFAULT_THRESHOLDS["tier0"]["winrate_30d_min"]))
        and trades >= float(t0.get("trades_30d_min", DEFAULT_THRESHOLDS["tier0"]["trades_30d_min"]))
    ):
        return "tier0"

    # tier1
    t1 = th.get("tier1") or {}
    if (
        roi >= float(t1.get("roi_30d_pct_min", DEFAULT_THRESHOLDS["tier1"]["roi_30d_pct_min"]))
        and (win is not None)
        and win >= float(t1.get("winrate_30d_min", DEFAULT_THRESHOLDS["tier1"]["winrate_30d_min"]))
        and trades >= float(t1.get("trades_30d_min", DEFAULT_THRESHOLDS["tier1"]["trades_30d_min"]))
    ):
        return "tier1"

    # tier2
    t2 = th.get("tier2") or {}
    if (
        roi >= float(t2.get("roi_30d_pct_min", DEFAULT_THRESHOLDS["tier2"]["roi_30d_pct_min"]))
        and trades >= float(t2.get("trades_30d_min", DEFAULT_THRESHOLDS["tier2"]["trades_30d_min"]))
    ):
        return "tier2"

    return "tier3"
