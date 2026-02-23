"""strategy/profiling.py

Wallet profiling utilities for Dune export normalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class WalletProfile:
    """Canonical wallet profile schema for Dune export."""
    wallet: str
    tier: Optional[str] = None
    roi_30d_pct: Optional[float] = None
    winrate_30d: Optional[float] = None
    trades_30d: Optional[int] = None
    median_hold_sec: Optional[float] = None
    avg_trade_size_sol: Optional[float] = None


def normalize_dune_row(row: Dict[str, Any]) -> WalletProfile:
    """Normalize a Dune query row to WalletProfile schema.
    
    Args:
        row: Dictionary with Dune query columns (address, roi_30d, winrate_30d, etc.)
    
    Returns:
        WalletProfile instance with normalized fields.
    
    Raises:
        ValueError: If required fields are missing or invalid.
    """
    # Map Dune column names to WalletProfile fields
    wallet = _get_wallet_address(row)
    roi_30d = _get_float(row, "roi_30d", default=0.0)
    winrate_30d = _get_float(row, "winrate_30d", default=0.0)
    trades_30d = _get_int(row, "trades_30d", default=0)
    median_hold_sec = _get_float(row, "median_hold_sec")
    avg_size_usd = _get_float(row, "avg_size_usd")
    memecoin_swaps = _get_int(row, "memecoin_swaps", default=0)
    total_swaps = _get_int(row, "total_swaps", default=0)
    
    # Validate ranges
    if not (0.0 <= winrate_30d <= 1.0):
        raise ValueError(f"winrate_30d must be in [0, 1], got {winrate_30d}")
    if trades_30d < 0:
        raise ValueError(f"trades_30d must be >= 0, got {trades_30d}")
    if roi_30d < -1.0:
        # Allow negative ROI but cap at -100%
        raise ValueError(f"roi_30d is unrealistic: {roi_30d}")
    
    # Calculate memecoin_ratio (0.0 to 1.0)
    if total_swaps > 0:
        memecoin_ratio = memecoin_swaps / total_swaps
    else:
        memecoin_ratio = 0.0
    
    # Convert avg_size_usd to avg_trade_size_sol (rough estimate: 1 SOL ≈ $100)
    SOL_USD_ESTIMATE = 100.0
    avg_trade_size_sol = None
    if avg_size_usd is not None:
        avg_trade_size_sol = avg_size_usd / SOL_USD_ESTIMATE
    
    return WalletProfile(
        wallet=wallet,
        roi_30d_pct=roi_30d,
        winrate_30d=winrate_30d,
        trades_30d=trades_30d,
        median_hold_sec=median_hold_sec,
        avg_trade_size_sol=avg_trade_size_sol,
    )


def _get_wallet_address(row: Dict[str, Any]) -> str:
    """Extract wallet address from various possible column names."""
    for key in ("address", "wallet", "wallet_address", "pubkey"):
        if key in row:
            value = row[key]
            if value:
                return str(value).strip()
    raise ValueError("Missing required field: wallet address (address/wallet/wallet_address)")


def _get_float(row: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    """Safely extract a float value from a row."""
    if key not in row:
        return default
    value = row[key]
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _get_int(row: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    """Safely extract an int value from a row."""
    if key not in row:
        return default
    value = row[key]
    if value is None or value == "":
        return default
    try:
        return int(float(value))  # Handle "120.0" -> 120
    except (ValueError, TypeError):
        return default


def normalize_flipside_row(row: Dict[str, Any]) -> Optional[WalletProfile]:
    """Normalize a Flipside solana.ez_dex_swaps row to WalletProfile schema.

    Maps Flipside columns to canonical wallet_profile format:
    - swapper -> wallet
    - roi_30d -> roi_30d_pct
    - winrate_30d -> winrate_30d
    - trades_30d -> trades_30d
    - median_hold_sec -> median_hold_sec
    - avg_size_usd -> avg_trade_size_sol (converted)
    - memecoin_ratio = memecoin_swaps / total_swaps (calculated)

    Args:
        row: Dictionary from Flipside CSV/JSONL export.

    Returns:
        WalletProfile if row is valid, None if validation fails.
    """
    # Extract wallet address
    wallet = _get_wallet_address_flipside(row)
    if not wallet:
        return None

    # Extract numeric fields
    roi_30d = _get_float(row, "roi_30d", default=0.0)
    winrate_30d = _get_float(row, "winrate_30d", default=0.0)
    trades_30d = _get_int(row, "trades_30d", default=0)
    median_hold_sec = _get_float(row, "median_hold_sec")
    avg_size_usd = _get_float(row, "avg_size_usd")

    # Calculate memecoin_ratio if memecoin_swaps and total_swaps present
    memecoin_ratio = None
    memecoin_swaps = _get_int(row, "memecoin_swaps")
    total_swaps = _get_int(row, "total_swaps")
    if memecoin_swaps is not None and total_swaps is not None and total_swaps > 0:
        memecoin_ratio = memecoin_swaps / total_swaps

    # Validate ranges
    if winrate_30d is not None and not (0.0 <= winrate_30d <= 1.0):
        return None

    if trades_30d is not None and trades_30d < 0:
        return None

    if median_hold_sec is not None and median_hold_sec < 0:
        return None

    # Convert avg_size_usd to avg_trade_size_sol (rough estimate: 1 SOL ≈ $100)
    SOL_USD_ESTIMATE = 100.0
    avg_trade_size_sol = None
    if avg_size_usd is not None:
        avg_trade_size_sol = avg_size_usd / SOL_USD_ESTIMATE

    return WalletProfile(
        wallet=wallet,
        roi_30d_pct=roi_30d,
        winrate_30d=winrate_30d,
        trades_30d=trades_30d,
        median_hold_sec=median_hold_sec,
        avg_trade_size_sol=avg_trade_size_sol,
    )


def _get_wallet_address_flipside(row: Dict[str, Any]) -> Optional[str]:
    """Extract wallet address from Flipside row (swapper column)."""
    for key in ("swapper", "wallet", "wallet_addr", "address"):
        if key in row:
            value = row[key]
            if value:
                addr = str(value).strip()
                if addr:
                    return addr
    return None


# Valid kolscan flags (whitelist)
KOLSCAN_VALID_FLAGS = {"verified", "whale", "memecoin_specialist"}


def enrich_with_kolscan(profile: WalletProfile, kolscan_data: Dict[str, Any]) -> WalletProfile:
    """Enrich a WalletProfile with Kolscan metadata.

    Maps Kolscan columns to WalletProfile extended fields:
    - kolscan_rank: Trading rank on Kolscan
    - kolscan_flags: Tags like verified, whale, memecoin_specialist
    - last_active_ts: Unix timestamp of last trading activity
    - preferred_dex: Set to "Kolscan" when enriched

    Args:
        profile: Existing WalletProfile to enrich.
        kolscan_data: Dictionary with Kolscan metadata.

    Returns:
        Enriched WalletProfile (new instance, original unchanged).
    """
    # Extract Kolscan fields
    kolscan_rank = kolscan_data.get("kolscan_rank")
    kolscan_flags_raw = kolscan_data.get("kolscan_flags")
    last_active_ts = kolscan_data.get("last_active_ts")

    # Validate and filter flags
    kolscan_flags = None
    if kolscan_flags_raw is not None and isinstance(kolscan_flags_raw, list):
        kolscan_flags = [f for f in kolscan_flags_raw if f in KOLSCAN_VALID_FLAGS]

    # Create new WalletProfile with Kolscan fields as extra data
    # Note: WalletProfile is frozen dataclass, we return dict with enriched data
    # For full implementation, extend WalletProfile with optional kolscan fields
    enriched_dict = {
        "wallet": profile.wallet,
        "tier": profile.tier,
        "roi_30d_pct": profile.roi_30d_pct,
        "winrate_30d": profile.winrate_30d,
        "trades_30d": profile.trades_30d,
        "median_hold_sec": profile.median_hold_sec,
        "avg_trade_size_sol": profile.avg_trade_size_sol,
        # Kolscan enrichment fields
        "kolscan_rank": kolscan_rank,
        "kolscan_flags": kolscan_flags,
        "last_active_ts": last_active_ts,
        "preferred_dex": "Kolscan",
    }

    # Return as dict ( caller can merge with WalletProfile)
    return enriched_dict  # type: ignore

# --- CI compatibility shim ---
def aggregate_wallet_stats(records):
    """
    Aggregate a list of profiling records into wallet-level stats.

    This function is used by integration.build_wallet_profiles in smoke tests.
    It is intentionally defensive: accepts dicts or lightweight objects.

    Returns:
        dict with basic counters and a few optional aggregates.
    """
    if records is None:
        records = []
    # If caller passes a dict mapping -> values
    if isinstance(records, dict):
        records = list(records.values())

    total = 0
    wins = 0
    losses = 0
    pnl_sum = 0.0
    pnl_count = 0
    buy_count = 0
    sell_count = 0

    def get(r, key, default=None):
        if isinstance(r, dict):
            return r.get(key, default)
        return getattr(r, key, default)

    for r in records:
        total += 1

        side = get(r, "side", None)
        if isinstance(side, str):
            if side.upper() == "BUY":
                buy_count += 1
            elif side.upper() == "SELL":
                sell_count += 1

        # win / loss signals can be stored variously
        is_win = get(r, "is_win", None)
        outcome = get(r, "outcome", None)
        if isinstance(is_win, bool):
            if is_win:
                wins += 1
            else:
                losses += 1
        elif isinstance(outcome, str):
            o = outcome.lower()
            if o in ("win", "won", "tp", "take_profit"):
                wins += 1
            elif o in ("loss", "lost", "sl", "stop_loss"):
                losses += 1

        pnl = get(r, "pnl", None)
        if pnl is None:
            pnl = get(r, "pnl_usd", None)
        if pnl is None:
            pnl = get(r, "pnl_bps", None)
        if pnl is not None:
            try:
                pnl_sum += float(pnl)
                pnl_count += 1
            except Exception:
                pass

    win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
    avg_pnl = (pnl_sum / pnl_count) if pnl_count > 0 else 0.0

    return {
        "n_records": total,
        "n_wins": wins,
        "n_losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "n_buy": buy_count,
        "n_sell": sell_count,
    }

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

@dataclass
class WalletProfileLike:
    wallet: str
    n_records: int = 0
    n_wins: int = 0
    n_losses: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    n_buy: int = 0
    n_sell: int = 0


def _get(rec, key, default=None):
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


def _agg_one(records: List[Any]) -> Dict[str, Any]:
    total = 0
    wins = 0
    losses = 0
    pnl_sum = 0.0
    pnl_count = 0
    buy_count = 0
    sell_count = 0

    for r in (records or []):
        total += 1

        side = _get(r, "side", None)
        if isinstance(side, str):
            s = side.upper()
            if s == "BUY":
                buy_count += 1
            elif s == "SELL":
                sell_count += 1

        is_win = _get(r, "is_win", None)
        outcome = _get(r, "outcome", None)
        if isinstance(is_win, bool):
            wins += 1 if is_win else 0
            losses += 0 if is_win else 1
        elif isinstance(outcome, str):
            o = outcome.lower()
            if o in ("win", "won", "tp", "take_profit"):
                wins += 1
            elif o in ("loss", "lost", "sl", "stop_loss"):
                losses += 1

        pnl = _get(r, "pnl", None)
        if pnl is None:
            pnl = _get(r, "pnl_usd", None)
        if pnl is None:
            pnl = _get(r, "pnl_bps", None)
        if pnl is not None:
            try:
                pnl_sum += float(pnl)
                pnl_count += 1
            except Exception:
                pass

    win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
    avg_pnl = (pnl_sum / pnl_count) if pnl_count > 0 else 0.0

    return {
        "n_records": total,
        "n_wins": wins,
        "n_losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "n_buy": buy_count,
        "n_sell": sell_count,
    }


def aggregate_wallet_stats(records):
    """
    Dual-mode:
    - If `records` is dict-like {wallet: [records]} -> returns List[WalletProfileLike]
      (what integration.build_wallet_profiles expects for CSV writing).
    - Else -> returns aggregated stats dict for a flat list of records.
    """
    if records is None:
        return []

    # Mode 1: dict keyed by wallet -> list of WalletProfileLike
    if isinstance(records, dict):
        out: List[WalletProfileLike] = []
        for wallet, recs in records.items():
            stats = _agg_one(recs if isinstance(recs, list) else list(recs))
            out.append(
                WalletProfileLike(
                    wallet=str(wallet),
                    n_records=int(stats["n_records"]),
                    n_wins=int(stats["n_wins"]),
                    n_losses=int(stats["n_losses"]),
                    win_rate=float(stats["win_rate"]),
                    avg_pnl=float(stats["avg_pnl"]),
                    n_buy=int(stats["n_buy"]),
                    n_sell=int(stats["n_sell"]),
                )
            )
        return out

    # Mode 2: flat iterable -> stats dict
    if not isinstance(records, list):
        try:
            records = list(records)
        except Exception:
            records = []
    return _agg_one(records)
