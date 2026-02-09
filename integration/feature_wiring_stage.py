"""Feature Wiring Integration Stage (PR-C.6).

Orchestrates feature building for trade candidates by:
1. Loading domain objects (WalletProfile, TokenSnapshot, PolymarketSnapshot)
2. Building feature vectors using ConcreteFeatureBuilder
3. Wiring features to the unified decision formula

This stage acts as the bridge between ingestion (domain objects)
and strategy (flat feature vectors for ML/heuristic models).
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.features.builder import ConcreteFeatureBuilder, FeatureVector
from strategy.logic import (
    WalletProfile,
    TokenSnapshot,
    PolymarketSnapshot,
    Decision,
)


logger = logging.getLogger(__name__)


@dataclass
class FeatureWiringConfig:
    """Configuration for feature wiring stage."""
    # Feature builder settings
    allow_unknown_features: bool = True
    
    # Feature filtering (optional)
    required_features: List[str] = field(default_factory=lambda: [
        "w_roi_30d",
        "w_winrate_30d", 
        "w_log_trades",
        "m_ret_1m",
        "m_vol_5m",
        "m_log_liq",
        "pm_bullish",
        "pm_risk",
        "interaction_score",
    ])


@dataclass
class WiredCandidate:
    """Trade candidate with computed features."""
    candidate_id: str
    wallet_address: str
    token_address: str
    features: FeatureVector
    wiring_success: bool
    error_message: Optional[str] = None


class FeatureWiringStage:
    """Integration stage for building and wiring features to candidates."""
    
    def __init__(
        self,
        config: Optional[FeatureWiringConfig] = None,
        builder: Optional[ConcreteFeatureBuilder] = None,
    ):
        """Initialize feature wiring stage.
        
        Args:
            config: Feature wiring configuration.
            builder: Feature builder instance (created if None).
        """
        self.config = config or FeatureWiringConfig()
        self.builder = builder or ConcreteFeatureBuilder(
            allow_unknown=self.config.allow_unknown_features
        )
    
    def process_candidate(
        self,
        candidate_id: str,
        wallet_address: str,
        token_address: str,
        wallet: Optional[WalletProfile] = None,
        token: Optional[TokenSnapshot] = None,
        polymarket: Optional[PolymarketSnapshot] = None,
    ) -> WiredCandidate:
        """Process a single trade candidate and build features.
        
        Args:
            candidate_id: Unique identifier for the candidate.
            wallet_address: Address of the wallet.
            token_address: Address of the token.
            wallet: Wallet profile data.
            token: Token snapshot data.
            polymarket: Polymarket sentiment data.
        
        Returns:
            WiredCandidate with computed features.
        """
        try:
            features = self.builder.build(
                wallet=wallet,
                token=token,
                polymarket=polymarket,
            )
            
            # Validate required features
            missing = [f for f in self.config.required_features if f not in features.features]
            if missing:
                logger.warning(
                    f"Candidate {candidate_id}: missing features: {missing}"
                )
            
            return WiredCandidate(
                candidate_id=candidate_id,
                wallet_address=wallet_address,
                token_address=token_address,
                features=features,
                wiring_success=True,
            )
        
        except Exception as e:
            logger.error(f"Candidate {candidate_id}: wiring failed: {e}")
            return WiredCandidate(
                candidate_id=candidate_id,
                wallet_address=wallet_address,
                token_address=token_address,
                features=FeatureVector(features={}),
                wiring_success=False,
                error_message=str(e),
            )
    
    def process_batch(
        self,
        candidates: List[Dict[str, Any]],
        wallets: Dict[str, WalletProfile],
        tokens: Dict[str, TokenSnapshot],
        polymarkets: Dict[str, PolymarketSnapshot],
    ) -> List[WiredCandidate]:
        """Process multiple candidates with their domain objects.
        
        Args:
            candidates: List of candidate dicts with candidate_id, wallet_address, token_address.
            wallets: Map of wallet_address -> WalletProfile.
            tokens: Map of token_address -> TokenSnapshot.
            polymarkets: Map of event_id -> PolymarketSnapshot.
        
        Returns:
            List of WiredCandidates in same order as input.
        """
        wired = []
        
        for cand in candidates:
            wallet = wallets.get(cand.get("wallet_address"))
            token = tokens.get(cand.get("token_address"))
            polymarket = polymarkets.get(cand.get("event_id"))
            
            wired_candidate = self.process_candidate(
                candidate_id=cand.get("candidate_id", "unknown"),
                wallet_address=cand.get("wallet_address", ""),
                token_address=cand.get("token_address", ""),
                wallet=wallet,
                token=token,
                polymarket=polymarket,
            )
            wired.append(wired_candidate)
        
        return wired
    
    def features_to_decision(
        self,
        wired_candidate: WiredCandidate,
    ) -> Decision:
        """Convert wired features to a trading decision.
        
        This is a placeholder for the actual decision formula wiring.
        In PR-S.2, this connects to the unified decision formula.
        
        Args:
            wired_candidate: Candidate with computed features.
        
        Returns:
            Decision based on feature values.
        """
        if not wired_candidate.wiring_success:
            return Decision(
                candidate_id=wired_candidate.candidate_id,
                outcome=Decision.SKIP.name,
                confidence=0.0,
                reject_reasons=[wired_candidate.error_message or "unknown"],
            )
        
        features = wired_candidate.features.features
        
        # Placeholder decision logic - connect to PR-S.2 unified formula
        # For now, use simple thresholds
        roi = features.get("w_roi_30d", 0)
        winrate = features.get("w_winrate_30d", 0)
        bullish = features.get("pm_bullish", 0)
        interaction = features.get("interaction_score", 0)
        
        # Simple heuristic: positive ROI + good winrate + bullish sentiment
        if roi > 0 and winrate > 0.5 and bullish > 0.6:
            outcome = Decision.ENTER.name
            confidence = min(roi + winrate + bullish, 1.0)
        elif roi < -0.5 or winrate < 0.3:
            outcome = Decision.SKIP.name
            confidence = 0.5
            reject_reasons = ["poor_wallet_metrics"]
        else:
            outcome = Decision.SKIP.name  # Default to skip for now
            confidence = 0.4
        
        return Decision(
            candidate_id=wired_candidate.candidate_id,
            outcome=outcome,
            confidence=confidence,
        )


def load_fixture_jsonl(
    fixture_path: str | Path,
) -> List[Dict[str, Any]]:
    """Load candidates from JSONL fixture file."""
    path = Path(fixture_path)
    items = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def save_wired_jsonl(
    wired: List[WiredCandidate],
    output_path: str | Path,
) -> None:
    """Save wired candidates to JSONL file."""
    path = Path(output_path)
    with open(path, "w") as f:
        for wc in wired:
            record = {
                "candidate_id": wc.candidate_id,
                "wiring_success": wc.wiring_success,
                "error_message": wc.error_message,
                "features": wc.features.features,
            }
            f.write(json.dumps(record) + "\n")


# Example usage
if __name__ == "__main__":
    import sys
    
    # Create sample data
    wallet = WalletProfile(
        wallet_address="7nY...SolanaWallet001",
        winrate=0.65,
        roi_mean=0.15,
        trade_count=50,
        pnl_ratio=1.5,
        avg_holding_time_sec=300,
        smart_money_score=0.72,
    )
    
    token = TokenSnapshot(
        token_address="So11111111111111111111111111111111111111112",
        symbol="SOL",
        liquidity_usd=250000.0,
        volume_24h=1500000.0,
        price=0.0002,
        holder_count=5000,
    )
    
    polymarket = PolymarketSnapshot(
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
    features = builder.build(wallet=wallet, token=token, polymarket=polymarket)
    
    print("Feature Vector:")
    for key, value in features.features.items():
        print(f"  {key}: {value:.4f}")
    
    print("\nFlat List (for ML models):")
    print(features.to_flat_list())
