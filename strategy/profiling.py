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



def _field(record: Any, name: str, default: Any = None) -> Any:
    """Read field from dict-like or object-like records."""
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)



def aggregate_wallet_stats(trades: list[Any]) -> list[WalletProfile]:
    """Aggregate normalized trades into wallet-level profile metrics.

    Expected per trade fields: wallet, pnl_usd, size_usd.
    Returns deterministic wallet-sorted output.
    """
    by_wallet: Dict[str, Dict[str, Any]] = {}

    for trade in trades:
        wallet_raw = _field(trade, "wallet")
        if wallet_raw is None:
            continue
        wallet = str(wallet_raw)

        bucket = by_wallet.setdefault(
            wallet,
            {
                "trades": 0,
                "wins": 0,
                "pnl_sum": 0.0,
                "size_sum": 0.0,
                "size_count": 0,
            },
        )

        bucket["trades"] += 1

        pnl = _field(trade, "pnl_usd")
        if pnl is not None:
            pnl_f = float(pnl)
            bucket["pnl_sum"] += pnl_f
            if pnl_f > 0:
                bucket["wins"] += 1

        size = _field(trade, "size_usd")
        if size is not None:
            size_f = float(size)
            if size_f > 0:
                bucket["size_sum"] += size_f
                bucket["size_count"] += 1

    profiles: list[WalletProfile] = []
    for wallet in sorted(by_wallet.keys()):
        b = by_wallet[wallet]
        trades_n = int(b["trades"])

        winrate = None
        if trades_n > 0:
            winrate = float(b["wins"]) / float(trades_n)

        roi_30d_pct = 0.0
        if b["size_sum"] > 0:
            roi_30d_pct = (float(b["pnl_sum"]) / float(b["size_sum"])) * 100.0

        avg_trade_size_sol = None
        if b["size_count"] > 0:
            avg_size_usd = float(b["size_sum"]) / float(b["size_count"])
            avg_trade_size_sol = avg_size_usd / 100.0

        profiles.append(
            WalletProfile(
                wallet=wallet,
                roi_30d_pct=roi_30d_pct,
                winrate_30d=winrate,
                trades_30d=trades_n,
                median_hold_sec=None,
                avg_trade_size_sol=avg_trade_size_sol,
            )
        )

    return profiles
