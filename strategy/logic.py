"""
strategy/logic.py - Unified Decision Logic

Pure logic for transforming state (Wallet + Token + Polymarket) into trading Signal.
Implements "One-Formula" decision: Hard Gates → P_model → EV → Regime → Limits.

HARD RULES:
- No RPC calls, print(), time.now() (time passed as argument)
- Input: WalletProfile, TokenSnapshot, PolymarketSnapshot (Data Classes)
- Output: Signal (Decision, Reason, params...)
- All thresholds via StrategyParams, no magic numbers
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple, Any, List
from datetime import datetime

from strategy.execution_math import (
    calculate_linear_impact_bps,
    MAX_SLIPPAGE_BPS
)


class Decision(Enum):
    """Signal decision enum."""
    ENTER = "ENTER"
    SKIP = "SKIP"


class Mode(Enum):
    """Trading mode enum."""
    M = "M"      # Normal mode
    L = "L"      # Large mode
    S = "S"      # Small mode
    XL = "XL"    # Extra large mode


@dataclass
class WalletProfile:
    """Wallet profile data class."""
    wallet_address: str
    winrate: float           # 0.0 - 1.0
    roi_mean: float          # Mean ROI across trades
    trade_count: int
    pnl_ratio: float         # Win/Loss ratio
    avg_holding_time_sec: float
    smart_money_score: float  # 0.0 - 1.0


@dataclass
class TokenSnapshot:
    """Token snapshot data class."""
    token_address: str
    symbol: str
    liquidity_usd: float
    volume_24h: float
    price: float
    holder_count: int
    # Security data
    is_honeypot: bool = False
    buy_tax_bps: int = 0
    sell_tax_bps: int = 0
    is_freezable: bool = False


@dataclass
class PolymarketSnapshot:
    """Polymarket snapshot data class."""
    event_id: str
    event_title: str
    outcome: str  # "Yes", "No", or probability
    probability: float  # 0.0 - 1.0
    volume_usd: float
    liquidity_usd: float
    bullish_score: float  # Derived bullish indicator


@dataclass
class StrategyParams:
    """Strategy configuration parameters. All thresholds are configurable."""
    # Hard gates
    min_liquidity_usd: float = 10000.0
    min_volume_24h: float = 5000.0
    min_wallet_winrate: float = 0.4
    min_wallet_roi: float = 0.0
    min_trade_count: int = 5
    max_buy_tax_bps: int = 1000  # 10%
    max_sell_tax_bps: int = 1000  # 10%
    
    # Model thresholds
    p0_enter: float = 0.5  # Min probability for entry
    p_skip: float = 0.3     # Probability threshold for skip
    
    # EV parameters
    default_winrate: float = 0.5
    coeff: float = 1.0      # EV multiplier
    k_p: float = 1.0        # Kelly fraction
    
    # Regime parameters
    regime_a: float = 1.0   # Bullish weight
    regime_b: float = 0.5   # Event risk weight
    bullish_threshold: float = 0.6
    
    # PR-PM.5: Risk regime adjustment alpha
    # Multiplier for risk_regime in edge correction formula
    # Formula: edge_final = edge_raw * (1 + alpha * risk_regime)
    regime_alpha: float = 0.20  # Range: [0.0, 0.5]
    
    # PR-RM.1: Polymarket-aware position sizing parameters
    # Formula: position_pct = base_position_pct * (1 + risk_beta * risk_regime)
    base_position_pct: float = 0.02          # 2% base position size
    risk_beta: float = 0.5                   # Regime sensitivity (0.5 = ±25% at ±1.0 regime)
    max_position_pct_risk_on: float = 0.05   # Max 5% in risk-on regime
    min_position_pct_risk_off: float = 0.01  # Min 1% in risk-off regime
    max_trade_size_usd: float = 5000.0       # Absolute max trade size in USD
    min_trade_size_usd: float = 500.0        # Min trade size to execute
    max_kelly_fraction: float = 0.25          # Kelly fraction cap
    allow_risk_aware_sizing: bool = True     # Enable adaptive position sizing
    
    # Position sizing (legacy)
    base_size_pct: float = 0.02  # 2% of portfolio
    max_size_pct: float = 0.10   # 10% max
    
    # TP/SL multipliers
    tp_multiplier: float = 2.0
    sl_multiplier: float = 1.0
    
    # Slippage estimation (PR-O.3)
    slippage_impact_scalar: float = 0.5  # Coefficient for slippage calculation
    max_slippage_bps: float = 1000.0  # Max acceptable slippage (10%)
    
    # Latency cost parameters (PR-R.1)
    base_latency_ms: float = 200.0  # Normal latency baseline (ms)
    latency_cost_slope: float = 0.1  # bps penalty per 1ms above baseline
    slot_lag_penalty_bps: float = 100.0  # bps penalty if slot lag detected
    max_latency_cost_bps: float = 1000.0  # Fail-safe cap for outages
    
    # TP/SL multipliers
    tp_multiplier: float = 2.0
    sl_multiplier: float = 1.0


@dataclass
class Signal:
    """Output signal data class."""
    decision: Decision
    reason: Optional[str] = None
    mode: Optional[Mode] = None
    size_pct: Optional[float] = None
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    ev_score: Optional[float] = None
    regime: Optional[float] = None
    
    # PR-PM.5: Risk regime integration fields
    # edge_raw: Raw edge before regime adjustment
    # edge_final: Edge after regime adjustment (edge_final = edge_raw * (1 + alpha * risk_regime))
    # risk_regime: Risk regime from Polymarket [-1.0, +1.0]
    # regime_alpha: Configurable weight for regime adjustment [0.0, 0.5]
    edge_raw: Optional[float] = None
    edge_final: Optional[float] = None
    risk_regime: Optional[float] = None
    regime_alpha: Optional[float] = None
    
    # PR-RM.1: Polymarket-aware position sizing fields
    # position_pct_raw: Base position percentage before regime adjustment
    # position_pct_adjusted: Final position percentage after regime adjustment
    # risk_regime_used: Risk regime value used for position sizing
    # position_sizing_method: Method used ("fixed", "risk_aware", "fallback")
    position_pct_raw: Optional[float] = None
    position_pct_adjusted: Optional[float] = None
    risk_regime_used: Optional[float] = None
    position_sizing_method: Optional[str] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)


# Reject reasons (imported from integration for canonical usage)
# These will be dynamically referenced to avoid circular imports
_REJECT_REASONS = {
    "token_liquidity_low": "token_liquidity_low",
    "token_volume_low": "token_volume_low",
    "wallet_winrate_low": "wallet_winrate_low",
    "wallet_roi_low": "wallet_roi_low",
    "wallet_trades_low": "wallet_trades_low",
    "high_tax": "high_tax",
    "honeypot": "honeypot",
    "ev_below_threshold": "ev_below_threshold",
    "regime_unfavorable": "regime_unfavorable",
    "p_below_enter": "p_below_enter",
}


# PR-PM.5: Risk Regime Adjustment Logic
def adjust_edge_for_regime(edge_raw: float, risk_regime: float, alpha: float) -> float:
    """
    Apply multiplicative regime correction to raw edge.
    
    Formula: edge_final = edge_raw * (1 + alpha * risk_regime)
    
    Args:
        edge_raw: Raw edge value before regime adjustment
        risk_regime: Risk regime from Polymarket [-1.0, +1.0]
        alpha: Configurable weight for regime adjustment [0.0, 0.5]
        
    Returns:
        Edge adjusted by regime. May become negative if risk_regime=-1.0 and alpha>0.
        
    Raises:
        AssertionError: If alpha out of [0.0, 0.5] or risk_regime out of [-1.0, +1.0]
    """
    assert 0.0 <= alpha <= 0.5, f"alpha={alpha} out of bounds [0.0, 0.5]"
    assert -1.001 <= risk_regime <= 1.001, f"risk_regime={risk_regime} out of bounds [-1.0, +1.0]"
    return edge_raw * (1.0 + alpha * risk_regime)


# PR-RM.1: Risk-Aware Position Sizing
def compute_risk_aware_position_pct(
    base_pct: float,
    risk_regime: float,
    risk_beta: float,
    min_pct: float,
    max_pct: float,
    allow_risk_aware: bool = True
) -> Tuple[float, str]:
    """
    Calculate adaptive position size based on risk regime.
    
    Formula: position_pct = base_pct * (1 + beta * risk_regime)
    
    Args:
        base_pct: Base position percentage (e.g., 0.02 for 2%)
        risk_regime: Polymarket regime [-1.0, +1.0]
        risk_beta: Sensitivity coefficient (0.5 = ±25% at ±1.0 regime)
        min_pct: Minimum position percentage (risk-off cap)
        max_pct: Maximum position percentage (risk-on cap)
        allow_risk_aware: Whether to apply regime adjustment
        
    Returns:
        Tuple of (adjusted_percentage, sizing_method)
        
    Examples:
        >>> compute_risk_aware_position_pct(0.02, 0.85, 0.5, 0.01, 0.05)
        (0.0285, 'risk_aware')
        
        >>> compute_risk_aware_position_pct(0.02, -0.92, 0.5, 0.01, 0.05)
        (0.01, 'risk_aware')  # Capped at min
        
        >>> compute_risk_aware_position_pct(0.02, 0.0, 0.5, 0.01, 0.05, allow_risk_aware=False)
        (0.02, 'fixed')  # Fixed when disabled
    """
    if not allow_risk_aware or risk_regime is None:
        return base_pct, "fixed"
    
    # Apply adaptive formula
    adjusted = base_pct * (1.0 + risk_beta * risk_regime)
    
    # Apply regime constraints
    adjusted = max(min_pct, min(max_pct, adjusted))
    
    # Apply absolute safety caps (1% to 5%)
    adjusted = max(0.01, min(0.05, adjusted))
    
    return adjusted, "risk_aware"


class CopyScalpStrategy:
    """
    Unified Decision Strategy implementing "One-Formula" logic.
    
    Decision Pipeline:
    1. Hard Gates (Wallet + Token checks)
    2. P_model (Probability model check)
    3. EV (Expected Value calculation)
    4. Regime (Polymarket regime adjustment)
    5. Limits (Position sizing)
    """
    
    def __init__(self, params: Optional[StrategyParams] = None):
        """Initialize strategy with configurable parameters."""
        self.params = params or StrategyParams()
    
    def polymarket_regime(self, polymarket: PolymarketSnapshot) -> float:
        """
        Calculate market regime based on Polymarket data.
        
        Formula: r = clip(a*(2*bullish-1) - b*event_risk, -1, 1)
        
        Where:
        - bullish = probability (0-1)
        - event_risk = 1 - liquidity_score
        
        Args:
            polymarket: Polymarket snapshot
            
        Returns:
            Regime value in [-1, 1]:
            - 1 = Strongly bullish
            - 0 = Neutral
            - -1 = Strongly bearish
        """
        # Bullish score: 2*prob - 1 (maps 0.5->0, 1->1, 0->-1)
        bullish = 2 * polymarket.probability - 1
        
        # Event risk based on liquidity (low liquidity = high risk)
        liquidity_score = min(1.0, polymarket.liquidity_usd / 100000.0)
        event_risk = 1.0 - liquidity_score
        
        # Regime calculation
        raw_regime = self.params.regime_a * bullish - self.params.regime_b * event_risk
        
        # Clip to [-1, 1]
        regime = max(-1.0, min(1.0, raw_regime))
        
        return regime
    
    def estimate_slippage_bps(
        self,
        size_usd: float,
        liquidity_usd: float
    ) -> float:
        """
        Estimate slippage in basis points based on trade size vs liquidity.
        
        Uses execution_math.calculate_linear_impact_bps with configurable scalar.
        
        Args:
            size_usd: Trade size in USD
            liquidity_usd: Pool liquidity in USD
            
        Returns:
            Slippage in basis points (0 to MAX_SLIPPAGE_BPS)
        """
        return calculate_linear_impact_bps(
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
            impact_scalar=self.params.slippage_impact_scalar
        )
    
    def passes_hard_gates(
        self,
        wallet: WalletProfile,
        token: TokenSnapshot
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if entry passes all hard gates.
        
        Returns:
            Tuple of (passed: bool, reject_reason: Optional[str])
        """
        # Token liquidity check
        if token.liquidity_usd < self.params.min_liquidity_usd:
            return False, "token_liquidity_low"
        
        # Token volume check
        if token.volume_24h < self.params.min_volume_24h:
            return False, "token_volume_low"
        
        # Wallet winrate check
        if wallet.winrate < self.params.min_wallet_winrate:
            return False, "wallet_winrate_low"
        
        # Wallet ROI check
        if wallet.roi_mean < self.params.min_wallet_roi:
            return False, "wallet_roi_low"
        
        # Wallet trade count check
        if wallet.trade_count < self.params.min_trade_count:
            return False, "wallet_trades_low"
        
        # Tax checks
        if token.buy_tax_bps > self.params.max_buy_tax_bps:
            return False, "high_tax"
        if token.sell_tax_bps > self.params.max_sell_tax_bps:
            return False, "high_tax"
        
        # Honeypot check
        if token.is_honeypot:
            return False, "honeypot"
        
        return True, None
    
    def compute_ev(
        self,
        winrate: float,
        rr_ratio: float,
        size_pct: float,
        cost_pct: float = 0.001
    ) -> float:
        """
        Calculate Expected Value (EV) for a trade.
        
        Formula: EV = p * (RR * size) - (1-p) * cost
        
        Args:
            winrate: Probability of winning (0-1)
            rr_ratio: Risk/Reward ratio
            size_pct: Position size as fraction of portfolio
            cost_pct: Trading cost as fraction of position
            
        Returns:
            EV as fraction of position size
        """
        win_pnl = rr_ratio * size_pct
        loss_pct = cost_pct
        
        ev = winrate * win_pnl - (1.0 - winrate) * loss_pct
        
        # Normalize by position size to get per-unit EV
        if size_pct > 0:
            ev_normalized = ev / size_pct
        else:
            ev_normalized = 0.0
        
        return ev_normalized
    
    def estimate_winrate(
        self,
        wallet: WalletProfile,
        token: TokenSnapshot,
        regime: float
    ) -> float:
        """
        Estimate probability of success based on wallet and regime.
        
        Combines wallet winrate with regime adjustment.
        """
        # Base winrate from wallet
        base_winrate = wallet.winrate
        
        # Regime adjustment: bullish regime boosts winrate
        regime_adjustment = regime * 0.1  # Max +/- 10% from regime
        
        # Smart money score bonus
        smart_money_bonus = wallet.smart_money_score * 0.05
        
        # Combined estimate
        estimated = base_winrate + regime_adjustment + smart_money_bonus
        
        # Clip to [0, 1]
        return max(0.0, min(1.0, estimated))
    
    def decide_on_wallet_buy(
        self,
        wallet: WalletProfile,
        token: TokenSnapshot,
        polymarket: Optional[PolymarketSnapshot],
        portfolio_value: float,
        timestamp: Optional[datetime] = None,
        # PR-PM.5: Risk regime integration parameters
        risk_regime: float = 0.0,
        skip_regime_adjustment: bool = False
    ) -> Signal:
        """
        Main decision method: decide whether to enter a trade.
        
        Args:
            wallet: Wallet profile data
            token: Token snapshot data
            polymarket: Optional Polymarket data
            portfolio_value: Current portfolio value in USD
            timestamp: Current time (passed as argument, not called)
            risk_regime: External risk regime from Polymarket [-1.0, +1.0]
            skip_regime_adjustment: If True, skip regime adjustment (edge_final = edge_raw)
            
        Returns:
            Signal with decision and parameters, including edge_raw and edge_final
        """
        # Step 1: Hard Gates
        passed, reason = self.passes_hard_gates(wallet, token)
        if not passed:
            return Signal(
                decision=Decision.SKIP,
                reason=reason or "unknown",
                metadata={"stage": "hard_gates"}
            )
        
        # Step 2: Polymarket Regime (if available) - combines with external risk_regime
        regime = 0.0  # Default neutral regime
        if polymarket:
            regime = self.polymarket_regime(polymarket)
        
        # Use external risk_regime if provided, otherwise use computed regime
        effective_risk_regime = risk_regime if risk_regime != 0.0 else regime
        
        # Check regime threshold
        if effective_risk_regime < -self.params.bullish_threshold:
            return Signal(
                decision=Decision.SKIP,
                reason="regime_unfavorable",
                regime=effective_risk_regime,
                risk_regime=effective_risk_regime,
                regime_alpha=self.params.regime_alpha,
                metadata={"stage": "regime"}
            )
        
        # Step 3: Estimate Winrate
        estimated_winrate = self.estimate_winrate(wallet, token, effective_risk_regime)
        
        # Check P_enter threshold
        if estimated_winrate < self.params.p0_enter:
            return Signal(
                decision=Decision.SKIP,
                reason="p_below_enter",
                ev_score=estimated_winrate,
                regime=effective_risk_regime,
                risk_regime=effective_risk_regime,
                regime_alpha=self.params.regime_alpha,
                metadata={"stage": "probability"}
            )
        
        # Step 4: Calculate EV
        rr_ratio = self.params.tp_multiplier / self.params.sl_multiplier
        base_size = self.params.base_size_pct
        
        ev_score = self.compute_ev(
            winrate=estimated_winrate,
            rr_ratio=rr_ratio,
            size_pct=base_size
        )
        
        # PR-PM.5: Edge calculation with regime adjustment
        # edge_raw: Raw edge before regime adjustment (same as ev_score for now)
        edge_raw = ev_score
        
        # edge_final: Edge after regime adjustment
        if skip_regime_adjustment:
            # Skip regime adjustment: edge_final = edge_raw
            edge_final = edge_raw
        else:
            # Apply regime correction: edge_final = edge_raw * (1 + alpha * risk_regime)
            edge_final = adjust_edge_for_regime(
                edge_raw=edge_raw,
                risk_regime=effective_risk_regime,
                alpha=self.params.regime_alpha
            )
        
        # Check EV threshold (simplified: need positive EV)
        if edge_final <= 0:
            return Signal(
                decision=Decision.SKIP,
                reason="ev_below_threshold",
                ev_score=edge_final,
                regime=effective_risk_regime,
                risk_regime=effective_risk_regime,
                edge_raw=edge_raw,
                edge_final=edge_final,
                regime_alpha=self.params.regime_alpha,
                metadata={"stage": "ev"}
            )
        
        # Step 5: Determine Mode based on regime
        # Higher regime = more aggressive mode
        # Boundary-inclusive tiers for deterministic scenario fixtures:
        # regime=0.70 is treated as strongly bullish (XL).
        if effective_risk_regime >= 0.7:
            mode = Mode.XL
            size_pct = min(self.params.max_size_pct, base_size * 1.5)
        elif effective_risk_regime >= 0.3:
            mode = Mode.L
            size_pct = min(self.params.max_size_pct, base_size * 1.2)
        else:
            mode = Mode.M
            size_pct = base_size
        
        # Step 6: Calculate TP/SL
        tp_pct = self.params.tp_multiplier * 0.01  # Convert to %
        sl_pct = self.params.sl_multiplier * 0.01
        
        # Return ENTER signal
        return Signal(
            decision=Decision.ENTER,
            reason=None,
            mode=mode,
            size_pct=size_pct,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            ev_score=edge_final,
            regime=effective_risk_regime,
            # PR-PM.5: New fields for risk regime integration
            risk_regime=effective_risk_regime,
            edge_raw=edge_raw,
            edge_final=edge_final,
            regime_alpha=self.params.regime_alpha,
            metadata={
                "stage": "entry",
                "wallet": wallet.wallet_address,
                "token": token.symbol,
                "estimated_winrate": estimated_winrate
            }
        )


# Convenience function
def make_decision(
    wallet: WalletProfile,
    token: TokenSnapshot,
    polymarket: Optional[PolymarketSnapshot],
    portfolio_value: float,
    params: Optional[StrategyParams] = None,
    # PR-PM.5: Risk regime integration parameters
    risk_regime: float = 0.0,
    skip_regime_adjustment: bool = False
) -> Signal:
    """
    Convenience function for single decision call.
    
    Args:
        wallet: Wallet profile data
        token: Token snapshot data
        polymarket: Optional Polymarket data
        portfolio_value: Current portfolio value in USD
        params: Optional strategy parameters
        risk_regime: External risk regime from Polymarket [-1.0, +1.0]
        skip_regime_adjustment: If True, skip regime adjustment
        
    Returns:
        Signal with decision and parameters
    """
    strat = CopyScalpStrategy(params)
    return strat.decide_on_wallet_buy(
        wallet=wallet,
        token=token,
        polymarket=polymarket,
        portfolio_value=portfolio_value,
        risk_regime=risk_regime,
        skip_regime_adjustment=skip_regime_adjustment
    )


if __name__ == "__main__":
    # Quick self-test
    print("CopyScalpStrategy Self-Test")
    print("=" * 40)
    
    strat = CopyScalpStrategy()
    
    # Test 1: Good wallet, good token
    wallet = WalletProfile(
        wallet_address="test_wallet",
        winrate=0.7,
        roi_mean=0.5,
        trade_count=20,
        pnl_ratio=2.0,
        avg_holding_time_sec=300,
        smart_money_score=0.8
    )
    
    token = TokenSnapshot(
        token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        symbol="USDC",
        liquidity_usd=100000,
        volume_24h=50000,
        price=1.0,
        holder_count=1000,
        is_honeypot=False,
        buy_tax_bps=0,
        sell_tax_bps=0,
        is_freezable=False
    )
    
    polymarket = PolymarketSnapshot(
        event_id="evt_123",
        event_title="Will SOL reach $200?",
        outcome="Yes",
        probability=0.7,
        volume_usd=50000,
        liquidity_usd=20000,
        bullish_score=0.7
    )
    
    signal = strat.decide_on_wallet_buy(wallet, token, polymarket, 10000.0)
    print(f"Good case: {signal.decision.value}")
    print(f"  Mode: {signal.mode}")
    print(f"  Size: {signal.size_pct}")
    print(f"  EV: {signal.ev_score}")
    print(f"  Regime: {signal.regime}")
    
    # Test 2: Bad wallet (low winrate)
    bad_wallet = WalletProfile(
        wallet_address="bad_wallet",
        winrate=0.2,
        roi_mean=-0.5,
        trade_count=5,
        pnl_ratio=0.5,
        avg_holding_time_sec=100,
        smart_money_score=0.1
    )
    
    signal2 = strat.decide_on_wallet_buy(bad_wallet, token, polymarket, 10000.0)
    print(f"\nBad wallet case: {signal2.decision.value}")
    print(f"  Reason: {signal2.reason}")
