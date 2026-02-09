"""
Pure Functions for Polymarket-Augmented Features.

Computes 4 features based on Polymarket data:
- pmkt_bullish_score: aggregated bullish probability score [-1.0, +1.0]
- pmkt_event_risk: binary flag for critical events within 3 days [0.0, 1.0]
- pmkt_volatility_zscore: z-score of probability volatility [-5.0, +5.0]
- pmkt_volume_spike_factor: volume spike relative to 24h mean [0.0, 10.0]

All functions are pure - only input data -> output features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


# Constants
WINDOW_6H_MS = 6 * 60 * 60 * 1000  # 6 hours in milliseconds
WINDOW_24H_MS = 24 * 60 * 60 * 1000  # 24 hours in milliseconds
WINDOW_3_DAYS = 3  # days


@dataclass
class PolymarketSnapshot:
    """Polymarket market snapshot."""
    ts: int  # timestamp in milliseconds
    market_id: str
    question: str
    p_yes: float  # probability of Yes (0.0 to 1.0)
    p_no: float  # probability of No (0.0 to 1.0)
    volume_usd: float
    event_date: int  # event expiration timestamp
    category_tags: List[str]


@dataclass
class PolymarketTokenMapping:
    """Token to Polymarket market mapping."""
    market_id: str
    token_mint: str
    token_symbol: str
    relevance_score: float  # 0.6 to 1.0
    mapping_type: str  # "exact_symbol", "thematic", "fuzzy_name"
    matched_keywords: List[str]

    def relevance_for_market(self, market_id: str) -> float:
        """Get relevance score for a market."""
        return self.relevance_score if self.market_id == market_id else 0.0


@dataclass
class EventRiskTimeline:
    """Event risk timeline for a market."""
    market_id: str
    high_event_risk: bool
    days_to_resolution: int
    risk_factors: List[str]


def compute_pmkt_bullish_score(
    snapshots: List[PolymarketSnapshot],
    mapping: Optional[PolymarketTokenMapping],
    window_ms: int = WINDOW_6H_MS,
) -> float:
    """
    Compute aggregated bullish score from Polymarket data.

    Formula: weighted sum of (p_yes - 0.5) * relevance * volume_norm
    - Weight = relevance_score * (0.7 + 0.3 * volume_normalized)
    - Signal = p_yes - 0.5 (range -0.5 to +0.5)
    - Result capped to [-1.0, +1.0]

    Args:
        snapshots: List of Polymarket snapshots
        mapping: Token-to-market mapping (None if no mapping)
        window_ms: Time window in milliseconds

    Returns:
        Bullish score in [-1.0, +1.0], or 0.0 if no data
    """
    if not snapshots:
        return 0.0

    now = max(s.ts for s in snapshots)
    window_start = now - window_ms

    # Filter recent snapshots within window
    recent = [
        s for s in snapshots
        if s.ts >= window_start and s.ts <= now
    ]

    if not recent:
        return 0.0

    # Get market IDs from mapping
    market_ids = {mapping.market_id} if mapping else set()

    # Filter to mapped markets if mapping exists
    if market_ids:
        recent = [s for s in recent if s.market_id in market_ids]
        if not recent:
            return 0.0

    # Normalize volumes
    volumes = [s.volume_usd for s in recent]
    min_vol = min(volumes)
    max_vol = max(volumes)
    vol_range = max_vol - min_vol if max_vol > min_vol else 1.0

    # Compute weighted sum
    weighted_sum = 0.0
    weight_sum = 0.0

    for s in recent:
        # Get relevance score
        rel_score = mapping.relevance_for_market(s.market_id) if mapping else 1.0

        # Normalize volume (0.0 to 1.0)
        vol_norm = (s.volume_usd - min_vol) / vol_range if vol_range > 0 else 0.5

        # Weight = relevance * (0.7 + 0.3 * volume_normalized)
        weight = rel_score * (0.7 + 0.3 * vol_norm)

        # Signal = p_yes - 0.5 (range -0.5 to +0.5)
        signal = s.p_yes - 0.5

        weighted_sum += signal * weight
        weight_sum += weight

    # Aggregate and clamp
    if weight_sum <= 0:
        return 0.0

    result = weighted_sum / weight_sum

    # Convert from [-0.5, +0.5] to [-1.0, +1.0] range
    result = result * 2.0

    return max(-1.0, min(1.0, result))


def compute_pmkt_event_risk(
    event_risk: Optional[EventRiskTimeline],
    window_days: int = WINDOW_3_DAYS,
) -> float:
    """
    Compute binary event risk flag.

    Returns 1.0 if high_event_risk=True AND days_to_resolution <= window_days,
    otherwise 0.0.

    Args:
        event_risk: Event risk timeline (None if no data)
        window_days: Maximum days to resolution for risk flag

    Returns:
        Risk flag in [0.0, 1.0]
    """
    if event_risk is None:
        return 0.0

    if not event_risk.high_event_risk:
        return 0.0

    if 0 <= event_risk.days_to_resolution <= window_days:
        return 1.0

    return 0.0


def compute_pmkt_volatility_zscore(
    snapshots: List[PolymarketSnapshot],
    window_ms: int = WINDOW_6H_MS,
) -> float:
    """
    Compute z-score of probability volatility.

    Calculates standard deviation of p_yes changes over the window,
    then computes z-score of the last change relative to that distribution.

    Args:
        snapshots: List of Polymarket snapshots
        window_ms: Time window in milliseconds

    Returns:
        Z-score in [-5.0, +5.0], or 0.0 if insufficient data
    """
    if not snapshots:
        return 0.0

    now = max(s.ts for s in snapshots)
    window_start = now - window_ms

    # Filter and sort by timestamp
    recent = sorted(
        [s for s in snapshots if s.ts >= window_start and s.ts <= now],
        key=lambda x: x.ts
    )

    # Need at least 5 points for meaningful volatility
    if len(recent) < 5:
        return 0.0

    # Calculate probability changes
    diffs = [
        recent[i + 1].p_yes - recent[i].p_yes
        for i in range(len(recent) - 1)
    ]

    if not diffs:
        return 0.0

    # Calculate mean and std of changes
    mean = sum(diffs) / len(diffs)

    if len(diffs) == 1:
        std = 0.0
    else:
        variance = sum((d - mean) ** 2 for d in diffs) / len(diffs)
        std = variance ** 0.5

    # Z-score of the last change
    last_diff = diffs[-1] if diffs else 0.0

    if std < 0.001:
        return 0.0

    zscore = last_diff / std

    # Cap to [-5.0, +5.0]
    return max(-5.0, min(5.0, zscore))


def compute_pmkt_volume_spike_factor(
    snapshots: List[PolymarketSnapshot],
    window_ms: int = WINDOW_24H_MS,
) -> float:
    """
    Compute volume spike factor.

    Ratio of current volume to 24h rolling mean.
    Current volume = max volume in the window (most recent significant trade).

    Args:
        snapshots: List of Polymarket snapshots
        window_ms: Time window in milliseconds

    Returns:
        Volume spike factor in [0.0, 10.0], or 1.0 (neutral) if no data
    """
    if not snapshots:
        return 1.0  # Neutral value when no data

    now = max(s.ts for s in snapshots)
    window_start = now - window_ms

    # Filter to window
    recent = [s for s in snapshots if s.ts >= window_start and s.ts <= now]

    if not recent:
        return 1.0  # Neutral value

    # Current volume = max volume in window (most recent significant volume)
    current_volume = max(s.volume_usd for s in recent)

    # Rolling mean
    volumes = [s.volume_usd for s in recent]
    rolling_mean = sum(volumes) / len(volumes)

    if rolling_mean <= 0:
        return 1.0  # Neutral

    factor = current_volume / rolling_mean

    # Cap to [0.0, 10.0]
    return max(0.0, min(10.0, factor))


# Batch computation for efficiency
def compute_all_pmkt_features(
    snapshots: List[PolymarketSnapshot],
    mapping: Optional[PolymarketTokenMapping],
    event_risk: Optional[EventRiskTimeline],
) -> dict:
    """
    Compute all 4 Polymarket features at once.

    Args:
        snapshots: List of Polymarket snapshots
        mapping: Token-to-market mapping
        event_risk: Event risk timeline

    Returns:
        Dict with all 4 features
    """
    return {
        "pmkt_bullish_score": compute_pmkt_bullish_score(snapshots, mapping),
        "pmkt_event_risk": compute_pmkt_event_risk(event_risk),
        "pmkt_volatility_zscore": compute_pmkt_volatility_zscore(snapshots),
        "pmkt_volume_spike_factor": compute_pmkt_volume_spike_factor(snapshots),
    }


# Example usage
if __name__ == "__main__":
    # Example snapshots
    snapshots = [
        PolymarketSnapshot(
            ts=1704067200000 + i * 3600000,  # hourly
            market_id="market_1",
            question="Will SOL exceed $100?",
            p_yes=0.6 + i * 0.04,  # increasing from 0.6 to 0.72
            p_no=0.4 - i * 0.04,
            volume_usd=10000 + i * 5000,
            event_date=1706755200000,
            category_tags=["crypto", "solana"],
        )
        for i in range(6)
    ]

    mapping = PolymarketTokenMapping(
        market_id="market_1",
        token_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        token_symbol="USDC",
        relevance_score=0.9,
        mapping_type="thematic",
        matched_keywords=["solana", "crypto"],
    )

    features = compute_all_pmkt_features(snapshots, mapping, None)
    print(features)
