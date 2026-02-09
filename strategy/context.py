"""
strategy/context.py

Pure logic for tracking smart money context in trade streams.
Provides sliding window tracking of Tier-0/1 wallet buys for token analysis.
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set, Tuple


@dataclass
class SmartMoneyEntry:
    """Record of a smart money wallet buy."""
    ts: int          # Unix timestamp in seconds
    wallet: str
    mint: str
    tier: str


@dataclass
class SmartMoneyConfig:
    """Configuration for smart money tracking."""
    window_sec: float = 60.0        # Sliding window in seconds
    target_tiers: Set[str] = field(default_factory=lambda: {"0", "1"})  # Tier-0 and Tier-1


class SmartMoneyTracker:
    """
    Tracks smart money (Tier-0/1 wallets) buys within a sliding window.

    Key properties:
    - Deterministic: Uses trade.ts for all window calculations (no time.now())
    - Efficient: Uses deque with automatic cleanup of expired entries
    - Memory-safe: Bounded by unique mint+wallet combinations in window

    Usage:
        tracker = SmartMoneyTracker()
        for trade in trades_sorted_by_ts:
            count = tracker.get_count(mint=trade.mint, current_ts=trade.ts, window_sec=60)
            if is_smart_money(trade.wallet):
                tracker.add(mint=trade.mint, wallet=trade.wallet, ts=trade.ts, tier=trade.tier)
    """

    def __init__(self, config: Optional[SmartMoneyConfig] = None):
        """Initialize tracker with optional custom config."""
        self.config = config or SmartMoneyConfig()
        # mint -> deque of (ts, wallet) entries
        self._history: Dict[str, Deque[Tuple[int, str]]] = {}

    def add(self, mint: str, wallet: str, ts: int, tier: str) -> None:
        """
        Record a smart money buy event.

        Args:
            mint: Token mint address
            wallet: Wallet address
            ts: Unix timestamp in seconds
            tier: Wallet tier (e.g., "0", "1", "2")
        """
        if tier not in self.config.target_tiers:
            return  # Not tracking this tier

        if mint not in self._history:
            self._history[mint] = deque()

        self._history[mint].append((ts, wallet))

    def get_count(self, mint: str, current_ts: int, window_sec: Optional[float] = None) -> int:
        """
        Count unique smart money wallets that bought this mint within the window.

        Args:
            mint: Token mint address
            current_ts: Current timestamp (from trade.ts)
            window_sec: Override window size (uses config default if None)

        Returns:
            Number of unique smart money wallets in the window
        """
        window = window_sec if window_sec is not None else self.config.window_sec
        cutoff = current_ts - window

        if mint not in self._history:
            return 0

        entries = self._history[mint]

        # Clean up expired entries from the left
        while entries and entries[0][0] < cutoff:
            entries.popleft()

        # Count unique wallets
        unique_wallets: Set[str] = set()
        for ts, wallet in entries:
            unique_wallets.add(wallet)

        return len(unique_wallets)

    def get_entries(self, mint: str, current_ts: int, window_sec: Optional[float] = None) -> List[SmartMoneyEntry]:
        """
        Get all smart money entries for a mint within the window.

        Args:
            mint: Token mint address
            current_ts: Current timestamp (from trade.ts)
            window_sec: Override window size (uses config default if None)

        Returns:
            List of SmartMoneyEntry records
        """
        window = window_sec if window_sec is not None else self.config.window_sec
        cutoff = current_ts - window

        if mint not in self._history:
            return []

        entries = self._history[mint]

        # Clean up expired entries from the left
        while entries and entries[0][0] < cutoff:
            entries.popleft()

        # Return as SmartMoneyEntry list (we only stored ts and wallet, tier not persisted in deque)
        return [
            SmartMoneyEntry(ts=ts, wallet=wallet, mint=mint, tier="unknown")
            for ts, wallet in entries
        ]

    def reset(self) -> None:
        """Clear all tracked history."""
        self._history.clear()

    def stats(self) -> Dict[str, Any]:
        """Get tracker statistics for debugging."""
        total_entries = sum(len(d) for d in self._history.values())
        unique_mints = len(self._history)
        return {
            "total_entries": total_entries,
            "unique_mints": unique_mints,
            "window_sec": self.config.window_sec,
            "target_tiers": list(self.config.target_tiers),
        }


def is_smart_money(wallet_tier: Optional[str], config: Optional[SmartMoneyConfig] = None) -> bool:
    """
    Check if a wallet tier is considered smart money.

    Args:
        wallet_tier: The wallet's tier (e.g., "0", "1", "2")
        config: Optional configuration with target tiers

    Returns:
        True if the tier is in target tiers
    """
    if wallet_tier is None:
        return False
    cfg = config or SmartMoneyConfig()
    return wallet_tier in cfg.target_tiers


def create_smart_money_features(
    tracker: SmartMoneyTracker,
    mint: str,
    current_ts: int,
    window_sec: float = 60.0,
) -> Dict[str, Any]:
    """
    Create smart money features for a trade.

    Args:
        tracker: SmartMoneyTracker instance
        mint: Token mint address
        current_ts: Current timestamp from trade.ts
        window_sec: Window size in seconds

    Returns:
        Dict with smart money features (e.g., {"count_60s": 2})
    """
    count = tracker.get_count(mint=mint, current_ts=current_ts, window_sec=window_sec)
    return {
        "count_60s": count,
    }
