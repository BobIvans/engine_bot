"""integration/execution_preflight.py

PR-6.1: execution preflight layer for estimating execution quality.

Pipeline:
  ENTRY candidate (BUY) -> execution gates (TTL/slippage/latency) -> fill_rate/slippage/latency metrics

Hard rules:
- Deterministic: no randomness, no "now", no external calls.
- Latency model: base_latency_ms + (lineno % (jitter_ms+1))
- Slippage model: slippage_bps_base + (qty_usd * slippage_bps_per_usd)
- Fill gates:
  - missing token_snapshot → missing_snapshot
  - missing wallet_profile → missing_wallet_profile
  - latency_ms > ttl_sec*1000 → ttl_expired
  - slippage_bps > max_slippage_bps → slippage_too_high
  - else → filled

Output: summary["execution_metrics"] with schema_version="execution_metrics.v1"
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

EXECUTION_SCHEMA_VERSION = "execution_metrics.v1"

# Fill failure reasons (grep anchors)
FAIL_TTL_EXPIRED = "ttl_expired"
FAIL_SLIPPAGE_TOO_HIGH = "slippage_too_high"
FAIL_MISSING_SNAPSHOT = "missing_snapshot"
FAIL_MISSING_WALLET_PROFILE = "missing_wallet_profile"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Best-effort attribute/dict getter."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    return default


def _compute_latency_ms(lineno: int, cfg: Dict[str, Any]) -> int:
    """Deterministic latency model.

    latency_ms = base_latency_ms + (lineno % (jitter_ms+1))
    """
    base_latency_ms = int(cfg.get("base_latency_ms", 0))
    jitter_ms = int(cfg.get("jitter_ms", 0))
    jitter = lineno % (jitter_ms + 1)
    return base_latency_ms + jitter


def _compute_slippage_bps(size_usd: float, cfg: Dict[str, Any]) -> float:
    """Deterministic slippage model.

    slippage_bps = slippage_bps_base + (size_usd * slippage_bps_per_usd)
    """
    slippage_bps_base = float(cfg.get("slippage_bps_base", 0))
    slippage_bps_per_usd = float(cfg.get("slippage_bps_per_usd", 0))
    return slippage_bps_base + (size_usd * slippage_bps_per_usd)


def execution_preflight(
    trades: List[Any],
    token_snapshots_store: Any,
    wallet_profiles_store: Any,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Run execution preflight on BUY trades.

    Args:
        trades: normalized trades (list of Trade objects or dicts).
        token_snapshots_store: TokenSnapshotStore instance (or None).
        wallet_profiles_store: WalletProfileStore instance (or None).
        cfg: configuration dict with execution_preflight section.

    Returns:
        execution_metrics dict (schema_version="execution_metrics.v1").
    """
    # Extract execution_preflight config
    exec_cfg = cfg.get("execution_preflight", {}) if isinstance(cfg, dict) else {}
    ttl_sec_default = int(exec_cfg.get("ttl_sec_default", 30))
    max_slippage_bps = int(exec_cfg.get("max_slippage_bps", 200))

    # Counters
    rows_total = len(trades)
    candidates = 0  # BUY rows that passed gates
    filled = 0
    fill_fail_by_reason: Dict[str, int] = {
        FAIL_TTL_EXPIRED: 0,
        FAIL_SLIPPAGE_TOO_HIGH: 0,
        FAIL_MISSING_SNAPSHOT: 0,
        FAIL_MISSING_WALLET_PROFILE: 0,
    }

    # For latency and slippage aggregation
    latency_values: List[int] = []
    slippage_values: List[float] = []

    for idx, t in enumerate(trades, start=1):
        # Only consider BUY trades
        side = str(_get(t, "side", "")).upper()
        if side != "BUY":
            continue

        # Get basic trade info
        mint = str(_get(t, "mint", "") or "")
        wallet = str(_get(t, "wallet", "") or "")
        if not mint or not wallet:
            continue

        # Get size_usd for slippage calculation
        size_usd_raw = _get(t, "size_usd", None)
        if size_usd_raw is None:
            size_usd_raw = _get(t, "qty_usd", None)
        try:
            size_usd = float(size_usd_raw) if size_usd_raw is not None else 0.0
        except Exception:
            size_usd = 0.0

        # Get TTL from mode config (use default if not specified)
        mode_name = "U"  # default mode
        extra = _get(t, "extra", None)
        if isinstance(extra, Mapping):
            m = extra.get("mode")
            if isinstance(m, str) and m.strip():
                mode_name = m

        modes = cfg.get("modes") if isinstance(cfg, dict) else {}
        mode_cfg = (modes or {}).get(mode_name, {}) if isinstance(modes, dict) else {}
        ttl_sec = int(mode_cfg.get("ttl_sec", ttl_sec_default))

        # Execution gates
        snap = None
        if token_snapshots_store is not None:
            if hasattr(token_snapshots_store, "get_latest"):
                snap = token_snapshots_store.get_latest(mint)
            elif hasattr(token_snapshots_store, "get"):
                snap = token_snapshots_store.get(mint)

        if snap is None:
            fill_fail_by_reason[FAIL_MISSING_SNAPSHOT] += 1
            continue

        wp = None
        if wallet_profiles_store is not None and hasattr(wallet_profiles_store, "get"):
            wp = wallet_profiles_store.get(wallet)
        if wp is None:
            fill_fail_by_reason[FAIL_MISSING_WALLET_PROFILE] += 1
            continue

        # Passed all prerequisite gates - this is a candidate
        candidates += 1

        # Compute deterministic latency
        lineno = idx  # use list index as deterministic lineno
        latency_ms = _compute_latency_ms(lineno=lineno, cfg=exec_cfg)
        latency_values.append(latency_ms)

        # Compute deterministic slippage
        slippage_bps = _compute_slippage_bps(size_usd=size_usd, cfg=exec_cfg)
        slippage_values.append(slippage_bps)

        # Check TTL gate
        ttl_ms = ttl_sec * 1000
        if latency_ms > ttl_ms:
            fill_fail_by_reason[FAIL_TTL_EXPIRED] += 1
            continue

        # Check slippage gate
        if slippage_bps > max_slippage_bps:
            fill_fail_by_reason[FAIL_SLIPPAGE_TOO_HIGH] += 1
            continue

        # Passed all execution gates - filled
        filled += 1

    # Calculate fill_rate
    fill_rate = float(filled) / float(candidates) if candidates else 0.0

    # Calculate latency percentiles
    latency_sorted = sorted(latency_values) if latency_values else []
    if latency_sorted:
        latency_p50 = latency_sorted[len(latency_sorted) // 2]
        latency_p90 = latency_sorted[int(len(latency_sorted) * 0.9)] if len(latency_sorted) >= 10 else latency_sorted[-1]
        latency_max = latency_sorted[-1]
    else:
        latency_p50 = 0
        latency_p90 = 0
        latency_max = 0

    # Calculate slippage percentiles
    slippage_sorted = sorted(slippage_values) if slippage_values else []
    if slippage_sorted:
        slippage_avg = sum(slippage_sorted) / len(slippage_sorted)
        slippage_p90 = slippage_sorted[int(len(slippage_sorted) * 0.9)] if len(slippage_sorted) >= 10 else slippage_sorted[-1]
        slippage_max = slippage_sorted[-1]
    else:
        slippage_avg = 0.0
        slippage_p90 = 0.0
        slippage_max = 0.0

    out: Dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "rows_total": int(rows_total),
        "candidates": int(candidates),
        "filled": int(filled),
        "fill_rate": float(fill_rate),
        "latency_ms": {
            "p50": int(latency_p50),
            "p90": int(latency_p90),
            "max": int(latency_max),
        },
        "slippage_bps": {
            "avg": float(slippage_avg),
            "p90": float(slippage_p90),
            "max": float(slippage_max),
        },
        "fill_fail_by_reason": {
            FAIL_TTL_EXPIRED: int(fill_fail_by_reason.get(FAIL_TTL_EXPIRED, 0)),
            FAIL_SLIPPAGE_TOO_HIGH: int(fill_fail_by_reason.get(FAIL_SLIPPAGE_TOO_HIGH, 0)),
            FAIL_MISSING_SNAPSHOT: int(fill_fail_by_reason.get(FAIL_MISSING_SNAPSHOT, 0)),
            FAIL_MISSING_WALLET_PROFILE: int(fill_fail_by_reason.get(FAIL_MISSING_WALLET_PROFILE, 0)),
        },
    }

    return out
