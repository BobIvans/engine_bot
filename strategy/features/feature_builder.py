"""Feature Builder for Trading Strategy.

Computes feature vectors for trades using various feature modules.
Integrates Smart Money Tracker for context-aware features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .smart_money import (
    SmartMoneyTracker,
    SmartMoneyState,
    TradeEvent,
    create_trade_from_dict,
)


# Global tracker instance (can be reset for testing)
_smart_money_tracker: Optional[SmartMoneyTracker] = None


def get_smart_money_tracker(window_sec: int = 300) -> SmartMoneyTracker:
    """Get or create the global smart money tracker instance."""
    global _smart_money_tracker
    if _smart_money_tracker is None:
        _smart_money_tracker = SmartMoneyTracker(window_sec=window_sec)
    return _smart_money_tracker


def reset_smart_money_tracker() -> None:
    """Reset the global tracker (for testing)."""
    global _smart_money_tracker
    _smart_money_tracker = None


@dataclass
class FeatureState:
    """Container for feature computation state."""
    smart_money_state: SmartMoneyState


def compute_features(
    trade: Dict[str, Any] | TradeEvent,
    state: FeatureState | None = None,
    now_ts: int | None = None,
    smart_money_window_sec: int = 300,
) -> Tuple[Dict[str, Any], FeatureState]:
    """Compute feature vector for a trade.

    Args:
        trade: Trade data as dict or TradeEvent.
        state: Optional FeatureState (created if None).
        now_ts: Current timestamp (uses trade.ts if None).
        smart_money_window_sec: Window size for smart money tracking.

    Returns:
        Tuple of (features_dict, updated_state).
    """
    # Normalize trade to TradeEvent
    if isinstance(trade, dict):
        trade_event = create_trade_from_dict(trade)
    else:
        trade_event = trade

    # Initialize state if needed
    if state is None:
        state = FeatureState(smart_money_state=[])

    # Use trade timestamp if now_ts not provided
    if now_ts is None:
        now_ts = trade_event.ts

    features: Dict[str, Any] = {}

    # === Smart Money Feature ===
    tracker = get_smart_money_tracker(window_sec=smart_money_window_sec)
    new_state, smart_features = tracker.compute_feature(
        state.smart_money_state,
        trade_event,
        now_ts,
        window_sec=smart_money_window_sec,
    )
    # Merge smart money features into main features dict
    features.update(smart_features)

    # Update state with new tracker state
    updated_state = FeatureState(smart_money_state=new_state)

    return features, updated_state


def compute_features_batch(
    trades: List[Dict[str, Any]],
    smart_money_window_sec: int = 300,
) -> Tuple[List[Dict[str, Any]], FeatureState]:
    """Compute features for a batch of trades sequentially.

    Args:
        trades: List of trade dicts.
        smart_money_window_sec: Window size for smart money tracking.

    Returns:
        Tuple of (features_list, final_state).
    """
    reset_smart_money_tracker()
    state = None
    results = []

    for trade in trades:
        features, state = compute_features(
            trade,
            state=state,
            now_ts=None,
            smart_money_window_sec=smart_money_window_sec,
        )
        results.append(features)

    return results, state


# Example usage (for testing only)
if __name__ == "__main__":
    import json

    # Example trades
    example_trades = [
        {
            "wallet": "WalletA",
            "wallet_tier": "T2",
            "ts": 1000,
            "mint": "SOL123",
            "tx_hash": "abc1",
            "side": "BUY",
            "price": 100.0,
            "size_usd": 1000.0,
        },
        {
            "wallet": "WalletB",
            "wallet_tier": "T1",
            "ts": 1010,
            "mint": "SOL123",
            "tx_hash": "def2",
            "side": "BUY",
            "price": 101.0,
            "size_usd": 2000.0,
        },
    ]

    results, final_state = compute_features_batch(example_trades)
    print(json.dumps(results, indent=2))
