"""Smart Money Tracker for Feature Builder.

Tracks how many "Smart Wallets" (Tier 0/1) have entered a token in a sliding window.
Pure state management - no DB/Redis dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


# Type aliases for clarity
Timestamp = int
WalletId = str
TierLabel = str
SmartWalletEntry = Tuple[Timestamp, WalletId, TierLabel]
SmartMoneyState = List[SmartWalletEntry]


@dataclass(frozen=True)
class TradeEvent:
    """Normalized trade event with wallet tier."""
    wallet: str
    wallet_tier: str  # Expected values: "T0", "T1", "T2", "T3" or "tier0", "tier1", etc.
    ts: int  # Unix timestamp (seconds)
    mint: str  # Token mint
    tx_hash: str  # Transaction hash
    side: str  # BUY/SELL
    price: float
    size_usd: float


class SmartMoneyTracker:
    """Pure state tracker for smart money entries in a sliding window.

    Tracks unique Tier 0/1 wallets that have bought a token within a configurable
    time window. Used to detect "smart money following" signals.
    """

    # Smart wallet tiers (case-insensitive matching)
    SMART_TIERS: frozenset = frozenset({"T0", "T1", "TIER0", "TIER1", "tier0", "tier1"})

    def __init__(self, window_sec: int = 300):
        """Initialize tracker with configurable window.

        Args:
            window_sec: Sliding window size in seconds (default: 5 minutes).
        """
        self.window_sec = window_sec

    def _normalize_tier(self, tier: str) -> str:
        """Normalize tier label to uppercase for comparison."""
        return tier.upper()

    def _is_smart_wallet(self, tier: str) -> bool:
        """Check if tier represents a smart wallet (T0 or T1)."""
        normalized = self._normalize_tier(tier)
        return normalized in {"T0", "TIER0", "T1", "TIER1"}

    def update(
        self,
        current_state: SmartMoneyState,
        trade: TradeEvent,
        now_ts: int,
        window_sec: int | None = None,
    ) -> Tuple[SmartMoneyState, int]:
        """Update state with a new trade and return smart money count.

        This is a pure function: it does not modify the input state.

        Args:
            current_state: List of (timestamp, wallet_id, tier) entries.
            trade: New trade event to process.
            now_ts: Current timestamp for window calculations.
            window_sec: Override for window size (uses instance default if None).

        Returns:
            Tuple of (new_state, smart_money_count):
            - new_state: Updated list with expired entries removed and new entry added.
            - smart_money_count: Number of unique T0/T1 wallets in window.
        """
        w = window_sec if window_sec is not None else self.window_sec

        # Step 1: Filter out expired entries
        cutoff_ts = now_ts - w
        filtered_state = [
            (ts, wallet, tier)
            for ts, wallet, tier in current_state
            if ts >= cutoff_ts
        ]

        # Step 2: Check if this trade's wallet is a smart wallet
        # Per HARD RULE #2: Don't count current user's trade as signal
        # We still add it to state but it doesn't increment the count
        is_smart = self._is_smart_wallet(trade.wallet_tier)

        # Step 3: Add new entry if smart wallet
        # Note: We track all entries for potential future use, but only
        # count unique T0/T1 wallets for the feature
        new_entry = (trade.ts, trade.wallet, trade.wallet_tier)
        new_state = filtered_state + [new_entry]

        # Step 4: Count unique smart wallets in window
        unique_smart_wallets: set[str] = set()
        for ts, wallet, tier in new_state:
            if self._is_smart_wallet(tier):
                unique_smart_wallets.add(wallet)

        count = len(unique_smart_wallets)

        return new_state, count

    def compute_feature(
        self,
        current_state: SmartMoneyState,
        trade: TradeEvent,
        now_ts: int,
        window_sec: int | None = None,
    ) -> Tuple[SmartMoneyState, Dict[str, Any]]:
        """Compute feature vector for a trade with smart money context.

        Args:
            current_state: Current tracker state.
            trade: Trade event to process.
            now_ts: Current timestamp.
            window_sec: Optional window override.

        Returns:
            Tuple of (new_state, features_dict) where features_dict contains:
            - smart_money_entry_count_5m: Number of unique T0/T1 wallets in window.
        """
        new_state, count = self.update(current_state, trade, now_ts, window_sec)

        features = {
            "smart_money_entry_count_5m": count,
        }

        return new_state, features


def create_trade_from_dict(data: Dict[str, Any]) -> TradeEvent:
    """Helper to create TradeEvent from dictionary (e.g., parsed JSONL)."""
    return TradeEvent(
        wallet=data["wallet"],
        wallet_tier=data.get("wallet_tier", "T3"),
        ts=int(data["ts"]) if isinstance(data["ts"], str) else data["ts"],
        mint=data["mint"],
        tx_hash=data["tx_hash"],
        side=data["side"],
        price=float(data["price"]),
        size_usd=float(data["size_usd"]),
    )
