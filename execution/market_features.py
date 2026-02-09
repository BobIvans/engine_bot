"""execution/market_features.py

PR-Z.3 Trailing Stop Dynamic Adjustment.

Extends market context with volatility and volume features for adaptive trailing stop.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional


@dataclass
class MarketContext:
    """Extended market context with volatility and volume features.
    
    These fields are used by TrailingAdjuster to dynamically adjust
    trailing stop distance based on market conditions.
    """
    ts: float                          # Timestamp (Unix seconds)
    mint: str                          # Token mint address
    price: Decimal                     # Current price
    
    # Volatility features (realized volatility, annualized from 5m/15m windows)
    rv_5m: float                       # RV 5m (e.g., 0.08 = 8% annualized)
    rv_15m: float                      # RV 15m
    
    # Volume features
    volume_delta_1m: float             # Normalized volume imbalance [-1.0, +1.0]
                                          # +1.0 = all buys, -1.0 = all sells
    volume_profile_score: float        # 0..1: how much current volume confirms trend
    
    # Liquidity features
    liquidity_usd: Optional[float] = None  # Pool liquidity in USD
    spread_bps: Optional[float] = None     # Bid-ask spread in basis points
    
    def validate(self) -> bool:
        """Validate that values are within reasonable bounds."""
        if not 0 <= self.rv_5m <= 0.5:  # Reject extreme volatility outliers
            return False
        if not -1.0 <= self.volume_delta_1m <= 1.0:
            return False
        if not 0.0 <= self.volume_profile_score <= 1.0:
            return False
        return True
