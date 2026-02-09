"""analysis/risk_regime.py

PR-PM.2 Risk Regime Computation - Pure Functions.

Computes scalar risk_regime [-1.0..+1.0] from Polymarket snapshots:
  +1.0 = maximum risk-on (aggressive regime)
  -1.0 = maximum risk-off (conservative regime)

All functions are pure - no side effects, deterministic output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class PolymarketSnapshot:
    """Represents a single Polymarket market snapshot."""
    market_id: str
    question: str
    p_yes: float  # Probability of YES outcome [0, 1]
    volume_usd: float
    category: str


@dataclass
class RegimeTimeline:
    """Output schema for risk regime computation."""
    ts: int
    risk_regime: float  # [-1.0, +1.0]
    bullish_markets: List[str]
    bearish_markets: List[str]
    confidence: float  # [0, 1]
    source_snapshot_id: str

    def __post_init__(self):
        """Validate range constraints."""
        assert -1.0 <= self.risk_regime <= 1.0, f"risk_regime out of range: {self.risk_regime}"
        assert 0.0 <= self.confidence <= 1.0, f"confidence out of range: {self.confidence}"


# Bullish question keywords (case-insensitive)
BULLISH_KEYWORDS = [
    "btc >",
    "bitcoin exceed",
    "crypto adoption",
    "bitcoin above",
    "eth >",
    "ethereum exceed",
    "bitcoin reach",
    "solana >",
]

# Bearish question keywords (case-insensitive)
BEARISH_KEYWORDS = [
    "crash",
    "drop below",
    "fall below",
    "bitcoin below",
    "crash below",
    "decline below",
    "lose ground",
    "risk-off",
]


def classify_market_bullishness(market: PolymarketSnapshot) -> Tuple[float, float]:
    """Classify market as bullish/bearish and return crypto relevance.

    Args:
        market: PolymarketSnapshot with question, p_yes, etc.

    Returns:
        Tuple of (bullish_score, crypto_relevance):
        - bullish_score: [0, 1] where >0.5 = bullish, <0.5 = bearish
        - crypto_relevance: {1.0, 0.6, 0.2} based on market type
    """
    question_lower = market.question.lower()

    # Check for bullish signals
    is_bullish = any(kw in question_lower for kw in BULLISH_KEYWORDS)

    # Check for bearish signals
    is_bearish = any(kw in question_lower for kw in BEARISH_KEYWORDS)

    # Determine bullish score
    if is_bullish and not is_bearish:
        bullish_score = market.p_yes  # High p_yes = bullish
    elif is_bearish and not is_bullish:
        bullish_score = 1.0 - market.p_yes  # Low p_yes = bullish (inverted)
    elif is_bullish and is_bearish:
        # Mixed signals - lean towards p_yes
        bullish_score = market.p_yes
    else:
        # Neutral - default to 0.5
        bullish_score = 0.5

    # Determine crypto relevance based on category and keywords
    crypto_keywords = ["btc", "bitcoin", "eth", "ethereum", "solana", "crypto"]
    is_crypto = any(kw in question_lower for kw in crypto_keywords)

    macro_keywords = ["s&p", "sp500", "nasdaq", "dow", "federal", "fed", "treasury", "macro"]
    is_macro = any(kw in question_lower for kw in macro_keywords)

    if is_crypto:
        crypto_relevance = 1.0
    elif is_macro:
        crypto_relevance = 0.6  # Macro with crypto correlation
    else:
        crypto_relevance = 0.2  # Low crypto relevance

    return bullish_score, crypto_relevance


def compute_risk_regime(snapshots: List[PolymarketSnapshot], ts: int, snapshot_id: str = "unknown") -> RegimeTimeline:
    """Compute risk regime from Polymarket snapshots.

    Pure function - same input always produces same output.

    Args:
        snapshots: List of PolymarketSnapshot objects
        ts: Unix timestamp for the output timeline
        snapshot_id: Source snapshot identifier

    Returns:
        RegimeTimeline with risk_regime in [-1.0, +1.0]
    """
    if not snapshots:
        # Empty input - neutral regime
        return RegimeTimeline(
            ts=ts,
            risk_regime=0.0,
            bullish_markets=[],
            bearish_markets=[],
            confidence=0.0,
            source_snapshot_id=snapshot_id,
        )

    # Sort by market_id for deterministic processing (fixed order = deterministic output)
    sorted_snapshots = sorted(snapshots, key=lambda m: m.market_id)

    # Calculate volumes for normalization
    volumes = [s.volume_usd for s in sorted_snapshots]
    min_vol = min(volumes)
    max_vol = max(volumes)
    vol_range = max_vol - min_vol if max_vol != min_vol else 1.0

    weighted_sum = 0.0
    bullish_markets: List[str] = []
    bearish_markets: List[str] = []

    for market in sorted_snapshots:
        bullish_score, crypto_relevance = classify_market_bullishness(market)

        # Normalize volume to [0, 1]
        volume_norm = (market.volume_usd - min_vol) / vol_range

        # Weighted contribution: (score - 0.5) shifts to [-0.5, +0.5]
        # Multiply by crypto_relevance and volume-weighted factor
        weight = crypto_relevance * (0.7 + 0.3 * volume_norm)
        contribution = (bullish_score - 0.5) * weight

        weighted_sum += contribution

        # Classify for output lists
        if bullish_score > 0.65:
            bullish_markets.append(market.question)
        elif bullish_score < 0.35:
            bearish_markets.append(market.question)

    # Normalize to [-1, +1] using tanh
    # Multiplier 2.0 provides reasonable sensitivity
    risk_regime = math.tanh(2.0 * weighted_sum)

    # Confidence is absolute value of regime
    confidence = abs(risk_regime)

    return RegimeTimeline(
        ts=ts,
        risk_regime=risk_regime,
        bullish_markets=bullish_markets,
        bearish_markets=bearish_markets,
        confidence=confidence,
        source_snapshot_id=snapshot_id,
    )


def validate_regime_output(regime: RegimeTimeline) -> bool:
    """Validate regime output satisfies all constraints.

    Args:
        regime: RegimeTimeline to validate

    Returns:
        True if valid, raises AssertionError otherwise
    """
    assert -1.001 < regime.risk_regime < 1.001, f"risk_regime out of range: {regime.risk_regime}"
    assert 0.0 <= regime.confidence <= 1.0, f"confidence out of range: {regime.confidence}"
    assert regime.ts >= 0, f"ts must be non-negative: {regime.ts}"
    assert isinstance(regime.bullish_markets, list), "bullish_markets must be a list"
    assert isinstance(regime.bearish_markets, list), "bearish_markets must be a list"
    return True
