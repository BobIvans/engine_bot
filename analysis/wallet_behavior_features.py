"""analysis/wallet_behavior_features.py

PR-ML.3: Wallet Behavior Features

Pure functions for computing behavioral pattern features based on historical trades.
All functions are deterministic and side-effect free.

Feature Contract:
- n_consecutive_wins: [0, 20] — consecutive winning trades (capped at 20)
- avg_hold_time_percentile: [0.0, 100.0] — percentile of median hold time vs population
- preferred_dex_concentration: [0.0, 1.0] — DEX activity concentration (1.0 = single DEX)
- co_trade_cluster_leader_score: [0.0, 1.0] — leadership score from co-trade clusters
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class TradeNorm:
    """Normalized trade record for feature computation.
    
    Extends Trade with entry/exit price tracking for profit calculation.
    """
    ts: int  # Unix timestamp in seconds
    wallet: str
    mint: str
    side: str  # "buy" | "sell"
    price: float  # USD price at trade time
    size_usd: float  # USD notional
    platform: str = ""  # DEX name
    entry_price_usd: Optional[float] = None  # Entry price for position
    exit_price_usd: Optional[float] = None  # Exit price for closed position
    tx_hash: str = ""


@dataclass(frozen=True)
class WalletProfile:
    """Wallet profile with behavioral metrics."""
    wallet_addr: str
    median_hold_sec: Optional[int] = None
    leader_score: Optional[float] = None
    cluster_label: Optional[int] = None


# Constants
MAX_CONSECUTIVE_WINS: int = 20
DEFAULT_PERCENTILE: float = 50.0
DEFAULT_CONCENTRATION: float = 0.5
DEFAULT_LEADER_SCORE: float = 0.5
WINDOW_TRADES: int = 20
DEX_WINDOW_TRADES: int = 50


def compute_n_consecutive_wins(
    wallet_addr: str,
    current_trade_ts: int,
    trades: List[TradeNorm],
    window_trades: int = WINDOW_TRADES
) -> int:
    """
    Number of consecutive winning trades before the current trade.
    
    A winning trade: exit_price_usd > entry_price_usd * 1.005 
    (accounts for ~0.5% fees).
    
    Args:
        wallet_addr: Wallet address to analyze
        current_trade_ts: Current trade timestamp (only before this trades)
        trades: List of historical trades
        window_trades: Maximum number of trades to consider
    
    Returns:
        Number of consecutive wins (capped at MAX_CONSECUTIVE_WINS)
    """
    # Filter trades for this wallet before current timestamp
    wallet_trades = sorted(
        [
            t for t in trades 
            if t.wallet == wallet_addr and t.ts < current_trade_ts
        ],
        key=lambda x: x.ts,
        reverse=True  # Most recent first
    )[:window_trades]
    
    if not wallet_trades:
        return 0
    
    # Count consecutive winning trades (from most recent backwards)
    streak = 0
    for trade in wallet_trades:
        is_win = _is_profitable_trade(trade)
        if is_win:
            streak += 1
        else:
            break
    
    return min(MAX_CONSECUTIVE_WINS, streak)


def _is_profitable_trade(trade: TradeNorm) -> bool:
    """Check if a trade is profitable (accounting for fees)."""
    if trade.exit_price_usd is not None and trade.entry_price_usd is not None:
        # Profit threshold: 0.5% to account for fees
        return trade.exit_price_usd > trade.entry_price_usd * 1.005
    return False


def compute_avg_hold_time_percentile(
    wallet_profile: Optional[WalletProfile],
    population_profiles: List[WalletProfile]
) -> float:
    """
    Percentile of wallet's median hold time vs population.
    
    Args:
        wallet_profile: Target wallet profile
        population_profiles: List of all wallet profiles for baseline
    
    Returns:
        Percentile [0.0, 100.0], default 50.0 if no data
    """
    if wallet_profile is None or wallet_profile.median_hold_sec is None:
        return DEFAULT_PERCENTILE
    
    # Extract all valid hold times from population
    all_hold_times = [
        p.median_hold_sec for p in population_profiles
        if p.median_hold_sec is not None and p.median_hold_sec > 0
    ]
    
    if not all_hold_times:
        return DEFAULT_PERCENTILE
    
    wallet_hold = wallet_profile.median_hold_sec
    
    # Compute percentile using linear interpolation
    sorted_holds = sorted(all_hold_times)
    rank = sum(1 for h in sorted_holds if h <= wallet_hold)
    percentile = (rank / len(sorted_holds)) * 100.0
    
    # Clamp to valid range
    return max(0.0, min(100.0, percentile))


def compute_preferred_dex_concentration(
    wallet_addr: str,
    trades: List[TradeNorm],
    window_trades: int = DEX_WINDOW_TRADES
) -> float:
    """
    Concentration of activity on top-1 DEX: fraction of trades on most-used DEX.
    
    Args:
        wallet_addr: Wallet address to analyze
        trades: List of historical trades
        window_trades: Maximum number of recent trades to consider
    
    Returns:
        Concentration ratio [0.0, 1.0], default 0.5 if no trades
    """
    wallet_trades = [
        t for t in trades if t.wallet == wallet_addr
    ][-window_trades:]
    
    if not wallet_trades:
        return DEFAULT_CONCENTRATION
    
    # Count DEX frequencies
    dex_counts: dict[str, int] = {}
    for trade in wallet_trades:
        dex = trade.platform or "unknown"
        dex_counts[dex] = dex_counts.get(dex, 0) + 1
    
    max_count = max(dex_counts.values())
    concentration = max_count / len(wallet_trades)
    
    # Clamp to valid range
    return max(0.0, min(1.0, concentration))


def compute_cluster_leader_score(
    wallet_profile: Optional[WalletProfile]
) -> float:
    """
    Leadership score from co-trade clusters (PR-WD.4).
    
    Args:
        wallet_profile: Target wallet profile with leader_score
    
    Returns:
        Leader score [0.0, 1.0], default 0.5 if no cluster data
    """
    if wallet_profile is None or wallet_profile.leader_score is None:
        return DEFAULT_LEADER_SCORE
    
    # Assume leader_score is already normalized to [0.0, 1.0]
    return max(0.0, min(1.0, wallet_profile.leader_score))


def compute_wallet_behavior_features(
    wallet_addr: str,
    current_trade_ts: int,
    trades: List[TradeNorm],
    wallet_profile: Optional[WalletProfile],
    population_profiles: List[WalletProfile]
) -> dict[str, float]:
    """
    Compute all wallet behavior features in a single call.
    
    Args:
        wallet_addr: Wallet address
        current_trade_ts: Current trade timestamp
        trades: List of historical trades
        wallet_profile: Wallet profile with metrics
        population_profiles: Population profiles for percentile baseline
    
    Returns:
        Dictionary with all behavior features
    """
    return {
        "n_consecutive_wins": compute_n_consecutive_wins(
            wallet_addr, current_trade_ts, trades
        ),
        "avg_hold_time_percentile": compute_avg_hold_time_percentile(
            wallet_profile, population_profiles
        ),
        "preferred_dex_concentration": compute_preferred_dex_concentration(
            wallet_addr, trades
        ),
        "co_trade_cluster_leader_score": compute_cluster_leader_score(
            wallet_profile
        ),
    }
