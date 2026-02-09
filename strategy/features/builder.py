"""Concrete Feature Builder for Trading Strategy.

Transforms domain objects (WalletProfile, TokenSnapshot, PolymarketSnapshot)
into flat feature vectors for the unified decision formula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from strategy.logic import WalletProfile, TokenSnapshot, PolymarketSnapshot


# Feature name constants
FEAT_W_ROI_30D = "w_roi_30d"
FEAT_W_WINRATE_30D = "w_winrate_30d"
FEAT_W_LOG_TRADES = "w_log_trades"
FEAT_M_RET_1M = "m_ret_1m"
FEAT_M_RET_5M = "m_ret_5m"
FEAT_M_VOL_5M = "m_vol_5m"
FEAT_M_LOG_LIQ = "m_log_liq"
FEAT_PM_BULLISH = "pm_bullish"
FEAT_PM_RISK = "pm_risk"
FEAT_INTERACTION = "interaction_score"


@dataclass
class FeatureVector:
    """Container for computed feature vector."""
    features: Dict[str, float]
    
    def get(self, key: str, default: float = float("nan")) -> float:
        """Get feature value with optional default."""
        return self.features.get(key, default)
    
    def to_flat_list(self) -> list:
        """Convert to ordered list for ML models."""
        ordered_keys = [
            FEAT_W_ROI_30D,
            FEAT_W_WINRATE_30D,
            FEAT_W_LOG_TRADES,
            FEAT_M_RET_1M,
            FEAT_M_RET_5M,
            FEAT_M_VOL_5M,
            FEAT_M_LOG_LIQ,
            FEAT_PM_BULLISH,
            FEAT_PM_RISK,
            FEAT_INTERACTION,
        ]
        return [self.features.get(k, float("nan")) for k in ordered_keys]


class ConcreteFeatureBuilder:
    """Builds feature vectors from domain objects.
    
    Transforms WalletProfile, TokenSnapshot, and PolymarketSnapshot
    into a flat Dict[str, float] for the unified decision formula.
    """
    
    def __init__(self, allow_unknown: bool = True):
        """Initialize builder.
        
        Args:
            allow_unknown: If True, missing features default to 0.0.
                          If False, missing features raise ValueError.
        """
        self.allow_unknown = allow_unknown
    
    def build(
        self,
        wallet: Optional[WalletProfile] = None,
        token: Optional[TokenSnapshot] = None,
        polymarket: Optional[PolymarketSnapshot] = None,
    ) -> FeatureVector:
        """Build feature vector from domain objects.
        
        Args:
            wallet: Wallet profile data (optional).
            token: Token snapshot data (optional).
            polymarket: Polymarket sentiment data (optional).
        
        Returns:
            FeatureVector with computed features.
        """
        features: Dict[str, float] = {}
        
        # Wallet features
        if wallet is not None:
            features[FEAT_W_ROI_30D] = self._safe_value(wallet.roi_mean)
            features[FEAT_W_WINRATE_30D] = self._safe_value(wallet.winrate)
            features[FEAT_W_LOG_TRADES] = self._safe_log(wallet.trade_count)
        elif not self.allow_unknown:
            raise ValueError("WalletProfile is required")
        
        # Token features
        if token is not None:
            features[FEAT_M_RET_1M] = self._safe_value(token.price)  # Simplified: price as ret proxy
            features[FEAT_M_RET_5M] = self._safe_value(token.price)   # Same for now
            features[FEAT_M_VOL_5M] = self._safe_log(token.volume_24h)
            features[FEAT_M_LOG_LIQ] = self._safe_log(token.liquidity_usd)
        elif not self.allow_unknown:
            raise ValueError("TokenSnapshot is required")
        
        # Polymarket features
        if polymarket is not None:
            features[FEAT_PM_BULLISH] = self._safe_value(polymarket.bullish_score)
            features[FEAT_PM_RISK] = 1.0 - self._safe_value(polymarket.probability)
        elif not self.allow_unknown:
            raise ValueError("PolymarketSnapshot is required")
        
        # Derived features
        features[FEAT_INTERACTION] = self._compute_interaction(features)
        
        return FeatureVector(features=features)
    
    def _safe_value(self, value: Optional[float]) -> float:
        """Convert value to float, defaulting to 0.0 if None or NaN."""
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0.0 if self.allow_unknown else float("nan")
        return float(value)
    
    def _safe_log(self, value: Optional[float]) -> float:
        """Compute log of value, handling edge cases.
        
        Returns 0.0 for None, 0, or negative values (log(1) = 0).
        """
        if value is None or value <= 0:
            return 0.0 if self.allow_unknown else float("nan")
        return math.log(value)
    
    def _compute_interaction(self, features: Dict[str, float]) -> float:
        """Compute interaction term from base features.
        
        interaction_score = w_winrate * pm_bullish
        """
        w_winrate = features.get(FEAT_W_WINRATE_30D, 0.0)
        pm_bullish = features.get(FEAT_PM_BULLISH, 0.0)
        return w_winrate * pm_bullish


# Convenience function for quick feature building
def build_feature_vector(
    wallet: Optional[WalletProfile] = None,
    token: Optional[TokenSnapshot] = None,
    polymarket: Optional[PolymarketSnapshot] = None,
    allow_unknown: bool = True,
) -> FeatureVector:
    """Quick helper to build feature vector."""
    builder = ConcreteFeatureBuilder(allow_unknown=allow_unknown)
    return builder.build(wallet=wallet, token=token, polymarket=polymarket)


# Example usage and self-test
if __name__ == "__main__":
    # Create sample domain objects
    sample_wallet = WalletProfile(
        wallet_address="7nY...SolanaWallet001",
        winrate=0.65,
        roi_mean=0.15,
        trade_count=50,
        pnl_ratio=1.5,
        avg_holding_time_sec=300,
        smart_money_score=0.72,
    )
    
    sample_token = TokenSnapshot(
        token_address="So11111111111111111111111111111111111111112",
        symbol="SOL",
        liquidity_usd=250000.0,
        volume_24h=1500000.0,
        price=0.0002,
        holder_count=5000,
    )
    
    sample_polymarket = PolymarketSnapshot(
        event_id="EVT001",
        event_title="Bitcoin ETF Approval",
        outcome="Yes",
        probability=0.78,
        volume_usd=50000.0,
        liquidity_usd=100000.0,
        bullish_score=0.78,
    )
    
    # Build features
    builder = ConcreteFeatureBuilder(allow_unknown=True)
    features = builder.build(
        wallet=sample_wallet,
        token=sample_token,
        polymarket=sample_polymarket,
    )
    
    print("Feature Vector:")
    for key, value in features.features.items():
        print(f"  {key}: {value:.4f}")
    
    print("\nFlat List (for ML models):")
    print(features.to_flat_list())
