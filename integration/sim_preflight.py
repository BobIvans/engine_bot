"""integration/sim_preflight.py

PR-5: deterministic offline "sim preflight" layer.

Pipeline:
  ENTRY candidate (BUY) -> +EV gate (ENTER/SKIP) -> deterministic exit sim (TP/SL/TIME) -> aggregates.

Hard rules:
- Deterministic: no randomness, no "now", no external calls.
- Future ticks are taken from the SAME trades list for the same mint, with ts > entry_ts, sorted by ts.
- Exit logic:
  - TP: price >= entry_price * (1 + tp_pct)
  - SL: price <= entry_price * (1 + sl_pct)  (sl_pct is negative)
  - TIME: after hold_sec_max seconds (if neither TP nor SL):
      close at last price in window; if no ticks in window -> entry_price.
- +EV gate (before simulation):
  - If token snapshot missing -> SKIP reason "missing_snapshot"
  - If wallet profile missing -> SKIP reason "missing_wallet_profile"
  - Else compute edge_bps deterministically; if edge_bps < min_edge_bps -> SKIP reason "ev_below_threshold"
  - Else ENTER

This module performs no I/O.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

SIM_SCHEMA_VERSION = "sim_metrics.v1"

SKIP_MISSING_SNAPSHOT = "missing_snapshot"
SKIP_MISSING_WALLET_PROFILE = "missing_wallet_profile"
SKIP_EV_BELOW_THRESHOLD = "ev_below_threshold"  # grep anchor


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Best-effort attribute/dict getter."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    return default


def _ts_to_seconds(ts: Any) -> float:
    """Parse trade ts into seconds.

    Supported:
    - numeric strings / numbers: treated as unix seconds
    - ISO-like strings: parsed as UTC (naive -> UTC)

    Deterministic: no current time.
    """
    if ts is None:
        return 0.0

    # numeric
    try:
        return float(ts)
    except Exception:
        pass

    s = str(ts).strip()
    if not s:
        return 0.0

    # Handle common 'Z'
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s

    # fromisoformat accepts "YYYY-MM-DD HH:MM:SS(.mmm)" and "T" separator
    try:
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        # Stable fallback: compare lexicographically elsewhere; here we return 0.
        return 0.0


def compute_edge_bps(
    trade: Any,
    token_snap: Any,
    wallet_profile: Any,
    cfg: Dict[str, Any],
    mode_name: str,
    p_model: Optional[float] = None,
) -> int:
    """Deterministic proxy for +EV gate.

    Formula (as specified):
      win_p = p_model if provided, else clamp(wallet_profile.winrate_30d, 0..1) (missing -> 0.0)
      tp = cfg_mode.tp_pct
      sl = abs(cfg_mode.sl_pct)
      gross_edge_pct = win_p*tp - (1-win_p)*sl
      costs_bps = int(token_snap.spread_bps) if present else 0
      edge_bps = int(round(gross_edge_pct * 10_000)) - costs_bps

    Args:
        trade: Trade object (not used in current formula, reserved for future use)
        token_snap: TokenSnapshot for spread/costs
        wallet_profile: WalletProfile for winrate (fallback if p_model not provided)
        cfg: Strategy config dict
        mode_name: Active mode name for TP/SL extraction
        p_model: Optional model probability (takes precedence over wallet winrate)

    Returns: signed integer bps.
    """
    # Use p_model if provided, otherwise fall back to wallet winrate
    if p_model is not None:
        win_p = _clamp(p_model, 0.0, 1.0)
    else:
        win_p_raw = _get(wallet_profile, "winrate_30d", 0.0)
        try:
            win_p = float(win_p_raw) if win_p_raw is not None else 0.0
        except Exception:
            win_p = 0.0
        win_p = _clamp(win_p, 0.0, 1.0)

    modes = cfg.get("modes") if isinstance(cfg, dict) else None
    mode_cfg = (modes or {}).get(mode_name, {}) if isinstance(modes, dict) else {}

    try:
        tp = float(mode_cfg.get("tp_pct", 0.0))
    except Exception:
        tp = 0.0
    try:
        sl = abs(float(mode_cfg.get("sl_pct", 0.0)))
    except Exception:
        sl = 0.0

    gross_edge_pct = (win_p * tp) - ((1.0 - win_p) * sl)

    costs_bps = 0
    spread = _get(token_snap, "spread_bps", None)
    if spread is not None:
        try:
            costs_bps = int(float(spread))
        except Exception:
            costs_bps = 0

    edge_bps = int(round(gross_edge_pct * 10_000)) - costs_bps
    return int(edge_bps)


def _simulate_exit(
    entry_price: float,
    entry_ts_sec: float,
    future_ticks: List[Tuple[float, float]],
    cfg_mode: Mapping[str, Any],
) -> Tuple[float, str]:
    """Simulate deterministic exit.

    Args:
      future_ticks: list of (ts_sec, price), sorted by ts_sec and filtered to same mint.

    Returns:
      (exit_price, reason) with reason in {TP,SL,TIME}
    """
    tp_pct = float(cfg_mode.get("tp_pct", 0.0))
    sl_pct = float(cfg_mode.get("sl_pct", 0.0))
    hold_sec_max = int(cfg_mode.get("hold_sec_max", 0))

    tp_level = entry_price * (1.0 + tp_pct)
    sl_level = entry_price * (1.0 + sl_pct)

    window_end = entry_ts_sec + float(hold_sec_max)

    last_price = entry_price
    saw_tick = False

    for ts_sec, px in future_ticks:
        if ts_sec <= entry_ts_sec:
            continue
        if ts_sec > window_end:
            break

        saw_tick = True
        last_price = px

        if px >= tp_level:
            return px, "TP"
        if px <= sl_level:
            return px, "SL"

    if not saw_tick:
        return entry_price, "TIME"
    return last_price, "TIME"


def preflight_and_simulate(
    trades_norm: List[Any],
    cfg: Dict[str, Any],
    token_snapshot_store: Any,
    wallet_profile_store: Any,
) -> Dict[str, Any]:
    """Run +EV preflight + deterministic TP/SL/TIME simulation.

    Args:
      trades_norm: normalized trades (Trade objects or dicts). Includes both entries and future ticks.

    Returns:
      sim_metrics dict (schema_version="sim_metrics.v1").
    """
    min_edge_bps = int(cfg.get("min_edge_bps", 0))

    # Prepare per-mint tick index from the same trades list.
    ticks_by_mint: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    any_mode_tag = False
    any_tier_tag = False

    for t in trades_norm:
        mint = str(_get(t, "mint", "") or "")
        if not mint:
            continue
        ts_sec = _ts_to_seconds(_get(t, "ts", ""))
        px_raw = _get(t, "price", None)
        try:
            px = float(px_raw)
        except Exception:
            continue
        ticks_by_mint[mint].append((ts_sec, px))

        extra = _get(t, "extra", None)
        if isinstance(extra, Mapping):
            if isinstance(extra.get("mode"), str):
                any_mode_tag = True
            if isinstance(extra.get("wallet_tier"), str):
                any_tier_tag = True

    for mint, arr in ticks_by_mint.items():
        arr.sort(key=lambda x: x[0])

    # Aggregate counters
    exit_reason_counts: Dict[str, int] = {"TP": 0, "SL": 0, "TIME": 0}
    skipped_by_reason: Dict[str, int] = {
        SKIP_MISSING_SNAPSHOT: 0,
        SKIP_MISSING_WALLET_PROFILE: 0,
        SKIP_EV_BELOW_THRESHOLD: 0,
    }

    total_pnl_usd = 0.0
    total_notional_usd = 0.0
    positions_total = 0
    positions_closed = 0
    wins = 0

    # Optional group aggregations
    by_mode: Dict[str, Dict[str, Any]] = defaultdict(lambda: _new_bucket())
    by_tier: Dict[str, Dict[str, Any]] = defaultdict(lambda: _new_bucket())

    for t in trades_norm:
        # Entry candidates are BUY trades
        side = str(_get(t, "side", "")).upper()
        if side != "BUY":
            continue

        mint = str(_get(t, "mint", "") or "")
        wallet = str(_get(t, "wallet", "") or "")
        if not mint or not wallet:
            continue

        entry_price_raw = _get(t, "price", None)
        try:
            entry_price = float(entry_price_raw)
        except Exception:
            continue

        entry_ts_sec = _ts_to_seconds(_get(t, "ts", ""))

        # +EV gate (SKIP/ENTER)
        snap = None
        if token_snapshot_store is not None:
            if hasattr(token_snapshot_store, "get_latest"):
                snap = token_snapshot_store.get_latest(mint)
            elif hasattr(token_snapshot_store, "get"):
                snap = token_snapshot_store.get(mint)

        if snap is None:
            # SKIP missing_snapshot
            skipped_by_reason[SKIP_MISSING_SNAPSHOT] = int(skipped_by_reason.get(SKIP_MISSING_SNAPSHOT, 0)) + 1
            continue

        wp = None
        if wallet_profile_store is not None and hasattr(wallet_profile_store, "get"):
            wp = wallet_profile_store.get(wallet)
        if wp is None:
            # SKIP missing_wallet_profile
            skipped_by_reason[SKIP_MISSING_WALLET_PROFILE] = int(skipped_by_reason.get(SKIP_MISSING_WALLET_PROFILE, 0)) + 1
            continue

        extra = _get(t, "extra", None)
        mode = "U"
        tier = None
        if isinstance(extra, Mapping):
            m = extra.get("mode")
            if isinstance(m, str) and m.strip():
                mode = m
            tr = extra.get("wallet_tier")
            if isinstance(tr, str) and tr.strip():
                tier = tr

        edge_bps = compute_edge_bps(trade=t, token_snap=snap, wallet_profile=wp, cfg=cfg, mode_name=mode)
        if edge_bps < min_edge_bps:
            # SKIP ev_below_threshold
            # reason string intentionally stable for grep/tests
            _ = SKIP_EV_BELOW_THRESHOLD
            skipped_by_reason[SKIP_EV_BELOW_THRESHOLD] = int(skipped_by_reason.get(SKIP_EV_BELOW_THRESHOLD, 0)) + 1
            continue

        positions_total += 1

        # Exit simulation
        mode_cfg = (cfg.get("modes") or {}).get(mode, {})
        fut = ticks_by_mint.get(mint, [])
        exit_price, reason = _simulate_exit(entry_price=entry_price, entry_ts_sec=entry_ts_sec, future_ticks=fut, cfg_mode=mode_cfg)

        # PnL uses notional = trade.qty_usd if present else 1.0 (in this repo: size_usd)
        notional_raw = _get(t, "qty_usd", None)
        if notional_raw is None:
            notional_raw = _get(t, "size_usd", None)
        try:
            notional = float(notional_raw) if notional_raw is not None else 1.0
        except Exception:
            notional = 1.0
        if notional <= 0:
            notional = 1.0

        pnl_usd = ((exit_price / entry_price) - 1.0) * notional

        positions_closed += 1
        total_pnl_usd += pnl_usd
        total_notional_usd += notional
        exit_reason_counts[reason] = int(exit_reason_counts.get(reason, 0)) + 1

        if pnl_usd > 0:
            wins += 1

        # Group buckets
        if any_mode_tag:
            _bucket_add(by_mode[mode], pnl_usd=pnl_usd, notional=notional, win=(pnl_usd > 0), reason=reason)
        if any_tier_tag and tier is not None:
            _bucket_add(by_tier[tier], pnl_usd=pnl_usd, notional=notional, win=(pnl_usd > 0), reason=reason)

    winrate = (wins / positions_closed) if positions_closed else 0.0
    roi_total = (total_pnl_usd / total_notional_usd) if total_notional_usd else 0.0
    avg_pnl_usd = (total_pnl_usd / positions_closed) if positions_closed else 0.0

    out: Dict[str, Any] = {
        "schema_version": SIM_SCHEMA_VERSION,
        "positions_total": int(positions_total),
        "positions_closed": int(positions_closed),
        "winrate": float(winrate),
        "roi_total": float(roi_total),
        "avg_pnl_usd": float(avg_pnl_usd),
        "skipped_by_reason": {
            SKIP_MISSING_SNAPSHOT: int(skipped_by_reason.get(SKIP_MISSING_SNAPSHOT, 0)),
            SKIP_MISSING_WALLET_PROFILE: int(skipped_by_reason.get(SKIP_MISSING_WALLET_PROFILE, 0)),
            SKIP_EV_BELOW_THRESHOLD: int(skipped_by_reason.get(SKIP_EV_BELOW_THRESHOLD, 0)),
        },
        "exit_reason_counts": {
            "TP": int(exit_reason_counts.get("TP", 0)),
            "SL": int(exit_reason_counts.get("SL", 0)),
            "TIME": int(exit_reason_counts.get("TIME", 0)),
        },
    }

    if any_mode_tag:
        out["by_mode"] = _finalize_groups(by_mode)
    if any_tier_tag:
        out["by_tier"] = _finalize_groups(by_tier)

    return out


def _new_bucket() -> Dict[str, Any]:
    return {
        "positions_closed": 0,
        "wins": 0,
        "total_pnl_usd": 0.0,
        "total_notional_usd": 0.0,
        "exit_reason_counts": {"TP": 0, "SL": 0, "TIME": 0},
    }


def _bucket_add(bucket: MutableMapping[str, Any], pnl_usd: float, notional: float, win: bool, reason: str) -> None:
    bucket["positions_closed"] = int(bucket.get("positions_closed", 0)) + 1
    bucket["wins"] = int(bucket.get("wins", 0)) + (1 if win else 0)
    bucket["total_pnl_usd"] = float(bucket.get("total_pnl_usd", 0.0)) + float(pnl_usd)
    bucket["total_notional_usd"] = float(bucket.get("total_notional_usd", 0.0)) + float(notional)

    erc = bucket.get("exit_reason_counts")
    if not isinstance(erc, dict):
        erc = {"TP": 0, "SL": 0, "TIME": 0}
        bucket["exit_reason_counts"] = erc
    erc[reason] = int(erc.get(reason, 0)) + 1


def _finalize_groups(groups: Mapping[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for k, b in groups.items():
        pc = int(b.get("positions_closed", 0))
        wins = int(b.get("wins", 0))
        pnl = float(b.get("total_pnl_usd", 0.0))
        notional = float(b.get("total_notional_usd", 0.0))
        winrate = (wins / pc) if pc else 0.0
        roi_total = (pnl / notional) if notional else 0.0
        avg_pnl_usd = (pnl / pc) if pc else 0.0

        erc = b.get("exit_reason_counts") if isinstance(b.get("exit_reason_counts"), dict) else {}
        out[str(k)] = {
            "positions_closed": pc,
            "winrate": float(winrate),
            "roi_total": float(roi_total),
            "avg_pnl_usd": float(avg_pnl_usd),
            "exit_reason_counts": {
                "TP": int(erc.get("TP", 0)),
                "SL": int(erc.get("SL", 0)),
                "TIME": int(erc.get("TIME", 0)),
            },
        }
    return out
