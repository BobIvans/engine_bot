"""features/trade_features.py

P0 feature builder (model-off friendly).

Contract:
- build_features(...) returns a JSON-serializable dict.
- Keys should be stable ("feature contract").
- Values should be floats/ints/bools/None.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from integration.trade_types import Trade
from integration.token_snapshot_store import TokenSnapshot
from integration.wallet_profile_store import WalletProfile
from strategy.survival import estimate_exit_probability_simple

# PR-ML.3: Wallet behavior features
from analysis.wallet_behavior_features import (
    TradeNorm,
    WalletProfile as WalletProfileBehavior,
    compute_n_consecutive_wins,
    compute_avg_hold_time_percentile,
    compute_preferred_dex_concentration,
    compute_cluster_leader_score,
)


def build_features(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
) -> Dict[str, Any]:
    f: Dict[str, Any] = {
        "price_usd": trade.price,
        "size_usd": trade.size_usd,
        "is_buy": 1 if trade.side == "BUY" else 0,
    }

    if snapshot is not None:
        f.update(
            {
                "liquidity_usd": snapshot.liquidity_usd,
                "volume_24h_usd": snapshot.volume_24h_usd,
                "spread_bps": snapshot.spread_bps,
            }
        )
    else:
        f.update({"liquidity_usd": None, "volume_24h_usd": None, "spread_bps": None})

    f.update(
        {
            "wallet_roi_30d_pct": (wallet_profile.roi_30d_pct if wallet_profile else trade.wallet_roi_30d_pct),
            "wallet_winrate_30d": (wallet_profile.winrate_30d if wallet_profile else trade.wallet_winrate_30d),
            "wallet_trades_30d": (wallet_profile.trades_30d if wallet_profile else trade.wallet_trades_30d),
        }
    )

    return f


def build_features_with_behavior(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
    trades_history: Optional[List[Trade]] = None,
    population_profiles: Optional[List[WalletProfile]] = None,
) -> Dict[str, Any]:
    """
    Build features including PR-ML.3 wallet behavior features.

    Args:
        trade: Current trade
        snapshot: Token snapshot
        wallet_profile: Wallet profile with metrics
        trades_history: Optional list of historical trades for behavior features
        population_profiles: Optional list of wallet profiles for percentile baseline

    Returns:
        Feature dict including wallet behavior features
    """
    # Start with base features
    f = build_features(trade, snapshot, wallet_profile)

    # Default values for PR-ML.3 behavior features
    f["n_consecutive_wins"] = 0
    f["avg_hold_time_percentile"] = 50.0
    f["preferred_dex_concentration"] = 0.5
    f["co_trade_cluster_leader_score"] = 0.5

    # Only compute if we have the required data
    if wallet_profile and trades_history:
        # Convert trades to TradeNorm format
        trades_norm = _convert_trades_to_norm(trades_history)

        # Parse current trade timestamp
        current_ts = _parse_timestamp(trade.ts)

        # Compute behavior features
        f["n_consecutive_wins"] = compute_n_consecutive_wins(
            wallet_profile.wallet,
            current_ts,
            trades_norm
        )

        f["preferred_dex_concentration"] = compute_preferred_dex_concentration(
            wallet_profile.wallet,
            trades_norm
        )

        f["co_trade_cluster_leader_score"] = compute_cluster_leader_score(
            _to_behavior_profile(wallet_profile)
        )

    if wallet_profile and population_profiles:
        f["avg_hold_time_percentile"] = compute_avg_hold_time_percentile(
            _to_behavior_profile(wallet_profile),
            [_to_behavior_profile(p) for p in population_profiles]
        )

    return f


def _convert_trades_to_norm(trades: List[Trade]) -> List[TradeNorm]:
    """Convert Trade objects to TradeNorm for behavior features."""
    result = []
    for t in trades:
        result.append(
            TradeNorm(
                ts=_parse_timestamp(t.ts),
                wallet=t.wallet,
                mint=t.mint,
                side=t.side,
                price=t.price,
                size_usd=t.size_usd,
                platform=t.platform,
            )
        )
    return result


def _parse_timestamp(ts: str) -> int:
    """Parse timestamp string to unix seconds."""
    if isinstance(ts, (int, float)):
        return int(ts)
    # Try parsing as ISO format
    if "T" in ts or "-" in ts:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except ValueError:
            pass
    # Fallback: assume already unix timestamp in milliseconds
    return int(ts)


def _to_behavior_profile(profile: WalletProfile) -> WalletProfileBehavior:
    """Convert WalletProfile to behavior profile format."""
    # Import here to avoid circular imports
    from integration.wallet_merge import WalletProfile as MergeProfile

    if isinstance(profile, MergeProfile):
        return WalletProfileBehavior(
            wallet_addr=profile.wallet_addr,
            median_hold_sec=profile.median_hold_sec,
            leader_score=getattr(profile, 'leader_score', None),
            cluster_label=getattr(profile, 'cluster_label', None),
        )
    # Handle the store WalletProfile type
    return WalletProfileBehavior(
        wallet_addr=profile.wallet if hasattr(profile, 'wallet') else str(profile),
        median_hold_sec=None,
        leader_score=None,
        cluster_label=None,
    )


# -----------------------------
# miniML feature contract v1
# -----------------------------

# This contract is used by `tools/export_training_dataset.py` and enforced by
# `scripts/features_smoke.sh`. Keep keys stable.
FEATURE_KEYS_V1 = [
    "f_trade_size_usd",
    "f_price",
    "f_side_is_buy",
    "f_token_liquidity_usd",
    "f_token_spread_bps",
    "f_wallet_roi_30d_pct",
    "f_wallet_winrate_30d",
    "f_wallet_trades_30d",
]


# -----------------------------
# miniML feature contract v2
# -----------------------------

# Feature v2 adds volatility, price impulse, and smart money signals.
# These features are extracted from TokenSnapshot.extra fields provided by Data-track.
FEATURE_KEYS_V2 = FEATURE_KEYS_V1 + [
    "f_token_vol_30s",       # volatility_30s from snapshot.extra
    "f_token_impulse_5m",   # price_change_5m_pct from snapshot.extra
    "f_smart_money_share",   # smart_buy_ratio from snapshot.extra
]


# -----------------------------
# miniML feature contract v3
# -----------------------------

# Feature v3 adds smart money context features from SmartMoneyTracker.
# These features track how many Tier-0/1 wallets bought the same token recently.
FEATURE_KEYS_V3 = FEATURE_KEYS_V2 + [
    "f_smart_money_count_60s",  # count of Tier-0/1 wallets buying this mint in last 60s
]


# -----------------------------
# miniML feature contract v4
# -----------------------------

# Feature v4 adds survival analysis features (exit probability).
# Based on wallet's historical median hold time.
FEATURE_KEYS_V4 = FEATURE_KEYS_V3 + [
    "f_wallet_exit_prob_60s",  # probability of exit within 60s based on median_hold_sec
]


# -----------------------------
# miniML feature contract v5
# -----------------------------

# Feature v5 adds Polymarket-augmented features.
# These features use Polymarket sentiment and event data for prediction.
FEATURE_KEYS_V5 = FEATURE_KEYS_V4 + [
    "f_pmkt_bullish_score",         # aggregated bullish probability [-1.0, +1.0]
    "f_pmkt_event_risk",          # binary event risk flag [0.0, 1.0]
    "f_pmkt_volatility_zscore",   # z-score of probability volatility [-5.0, +5.0]
    "f_pmkt_volume_spike_factor", # volume spike factor [0.0, 10.0]
]


# -----------------------------
# miniML feature contract v5
# -----------------------------

# Feature v5 adds Polymarket-augmented features.
# These features use Polymarket sentiment and event data for prediction.
FEATURE_KEYS_V5 = FEATURE_KEYS_V4 + [
    "f_pmkt_bullish_score",         # aggregated bullish probability [-1.0, +1.0]
    "f_pmkt_event_risk",            # binary event risk flag [0.0, 1.0]
    "f_pmkt_volatility_zscore",      # z-score of probability volatility [-5.0, +5.0]
    "f_pmkt_volume_spike_factor",    # volume spike factor [0.0, 10.0]
]


def build_features_v1(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
) -> Dict[str, float]:
    """Return a stable set of numeric features for training/analysis.

    Requirements:
    - Always returns all FEATURE_KEYS_V1.
    - Missing data is encoded as 0.0.
    """

    def _f(x: Any) -> float:
        try:
            if x is None:
                return 0.0
            if isinstance(x, bool):
                return 1.0 if x else 0.0
            return float(x)
        except Exception:
            return 0.0

    side = str(getattr(trade, "side", "")).upper()
    out: Dict[str, float] = {
        "f_trade_size_usd": _f(getattr(trade, "size_usd", 0.0)),
        "f_price": _f(getattr(trade, "price", 0.0)),
        "f_side_is_buy": 1.0 if side == "BUY" else 0.0,
        "f_token_liquidity_usd": _f(getattr(snapshot, "liquidity_usd", 0.0) if snapshot else 0.0),
        "f_token_spread_bps": _f(getattr(snapshot, "spread_bps", 0.0) if snapshot else 0.0),
        "f_wallet_roi_30d_pct": _f(
            getattr(wallet_profile, "roi_30d_pct", None)
            if wallet_profile
            else getattr(trade, "wallet_roi_30d_pct", 0.0)
        ),
        "f_wallet_winrate_30d": _f(
            getattr(wallet_profile, "winrate_30d", None)
            if wallet_profile
            else getattr(trade, "wallet_winrate_30d", 0.0)
        ),
        "f_wallet_trades_30d": _f(
            getattr(wallet_profile, "trades_30d", None)
            if wallet_profile
            else getattr(trade, "wallet_trades_30d", 0.0)
        ),
    }

    # Defensive: ensure all keys exist.
    for k in FEATURE_KEYS_V1:
        out.setdefault(k, 0.0)
    return out


def _get_from_extra(extra: Optional[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    """Safely extract a float value from snapshot.extra dict.

    Args:
        extra: TokenSnapshot.extra dict (may be None)
        key: Key to look up in extra
        default: Default value if key not found or value is None

    Returns:
        float value or default
    """
    if extra is None:
        return default
    try:
        val = extra.get(key)
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_from_dict(obj: Optional[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    """Safely extract a float value from a dict.

    Args:
        obj: Dict to extract from (may be None)
        key: Key to look up
        default: Default value if key not found or value is None

    Returns:
        float value or default
    """
    if obj is None:
        return default
    try:
        val = obj.get(key)
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def build_features_v2(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
) -> Dict[str, float]:
    """Return an extended set of numeric features for training/analysis.

    Feature v2 includes all v1 features plus:
    - f_token_vol_30s: volatility_30s (from snapshot.extra)
    - f_token_impulse_5m: price_change_5m_pct (from snapshot.extra)
    - f_smart_money_share: smart_buy_ratio (from snapshot.extra)

    Requirements:
    - Always returns all FEATURE_KEYS_V2.
    - Missing data is encoded as 0.0.
    """
    # Build v1 features first
    out = build_features_v1(trade, snapshot, wallet_profile)

    # Extract v2 features from snapshot.extra
    extra = snapshot.extra if snapshot else None

    out["f_token_vol_30s"] = _get_from_extra(extra, "volatility_30s")
    out["f_token_impulse_5m"] = _get_from_extra(extra, "price_change_5m_pct")
    out["f_smart_money_share"] = _get_from_extra(extra, "smart_buy_ratio")

    # Defensive: ensure all v2 keys exist
    for k in FEATURE_KEYS_V2:
        out.setdefault(k, 0.0)

    return out


def build_features_v3(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
) -> Dict[str, float]:
    """Return an extended set of numeric features including smart money context.

    Feature v3 includes all v2 features plus:
    - f_smart_money_count_60s: count of Tier-0/1 wallets buying this mint in last 60s

    Requirements:
    - Always returns all FEATURE_KEYS_V3.
    - Missing data is encoded as 0.0.
    """
    # Build v2 features first
    out = build_features_v2(trade, snapshot, wallet_profile)

    # Extract smart_money_features from trade.extra
    extra = getattr(trade, "extra", None) or {}
    smart_money_features = extra.get("smart_money_features")

    # Handle both dict and non-dict cases
    if isinstance(smart_money_features, dict):
        out["f_smart_money_count_60s"] = _get_from_dict(smart_money_features, "count_60s")
    else:
        out["f_smart_money_count_60s"] = 0.0

    # Defensive: ensure all v3 keys exist
    for k in FEATURE_KEYS_V3:
        out.setdefault(k, 0.0)

    return out


def build_features_v4(
    trade: Trade,
    snapshot: Optional[TokenSnapshot],
    wallet_profile: Optional[WalletProfile],
) -> Dict[str, float]:
    """Return an extended set of numeric features including survival analysis.

    Feature v4 includes all v3 features plus:
    - f_wallet_exit_prob_60s: probability of exit within 60s based on median_hold_sec

    Requirements:
    - Always returns all FEATURE_KEYS_V4.
    - Missing data is encoded as 0.0.
    """
    # Build v3 features first
    out = build_features_v3(trade, snapshot, wallet_profile)

    # Extract median_hold_sec from wallet_profile
    median_hold_sec = None
    if wallet_profile is not None:
        median_hold_sec = getattr(wallet_profile, "median_hold_sec", None)

    # Calculate exit probability using survival model
    out["f_wallet_exit_prob_60s"] = estimate_exit_probability_simple(
        median_hold_sec=median_hold_sec,
        window_sec=60.0,
        default_prob=0.5,
    )

    # Defensive: ensure all v4 keys exist
    for k in FEATURE_KEYS_V4:
        out.setdefault(k, 0.0)

    return out
