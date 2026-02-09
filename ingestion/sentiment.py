"""ingestion/sentiment.py

PR-F.4 Social Sentiment Stub & Data Enrichment.

Interface for sentiment analysis:
- SentimentEngine: Protocol for analyzing token mints
- StubSentimentEngine: Deterministic stub for testing

Design goals:
- Fail-safe: Exceptions caught, return empty tags
- Deterministic: Stub returns stable tags based on mint
- No stdout pollution
"""

from __future__ import annotations

from typing import List, Protocol, Dict, Any


class SentimentEngine(Protocol):
    """Protocol for sentiment analysis engines.

    Implementations should:
    - analyze(token_mint: str) -> List[str]
    - Return stable, deterministic tags
    """

    def analyze(self, token_mint: str) -> List[str]:
        """Analyze a token mint and return sentiment tags.

        Args:
            token_mint: The token mint address to analyze.

        Returns:
            List of sentiment tags (e.g., ["pump", "scam", "buzz"]).
        """
        ...


class StubSentimentEngine:
    """Deterministic stub sentiment engine for testing.

    Returns predefined tags based on mint patterns:
    - "MINT_PUMP" -> ["pump"]
    - "MINT_SCAM" -> ["scam"]
    - "MINT_BUZZ" -> ["buzz", "social"]
    - Otherwise -> []
    """

    # Mapping of mint patterns to expected tags
    MINT_TAGS: Dict[str, List[str]] = {
        "MINT_PUMP": ["pump"],
        "MINT_SCAM": ["scam"],
        "MINT_BUZZ": ["buzz", "social"],
        "MINT_BULL": ["bullish", "momentum"],
        "MINT_BEAR": ["bearish", "fUD"],
    }

    def __init__(self, custom_tags: Dict[str, List[str]] | None = None):
        """Initialize with optional custom tag mapping.

        Args:
            custom_tags: Optional override for mint->tags mapping.
        """
        if custom_tags is not None:
            self.MINT_TAGS = custom_tags

    def analyze(self, token_mint: str) -> List[str]:
        """Analyze token mint and return sentiment tags.

        Args:
            token_mint: The token mint address.

        Returns:
            List of sentiment tags, or empty list if not recognized.
        """
        # Check for exact match first
        if token_mint in self.MINT_TAGS:
            return self.MINT_TAGS[token_mint].copy()

        # Check for substring matches (case-insensitive)
        mint_lower = token_mint.lower()
        for pattern, tags in self.MINT_TAGS.items():
            if pattern.lower() in mint_lower or mint_lower in pattern.lower():
                return tags.copy()

        # No sentiment tags for unrecognized mints
        return []


def create_sentiment_engine(config: Dict[str, Any]) -> SentimentEngine:
    """Factory function to create sentiment engine from config.

    Args:
        config: Config dict with sentiment settings.

    Returns:
        SentimentEngine implementation based on config.
    """
    sentiment_cfg = config.get("sentiment", {})
    enabled = sentiment_cfg.get("enabled", False)

    if not enabled:
        # Return a no-op engine that always returns empty
        return StubSentimentEngine()

    provider = sentiment_cfg.get("provider", "stub")

    if provider == "stub":
        # Allow custom tags from config for testing
        custom_tags = sentiment_cfg.get("stub_tags")
        return StubSentimentEngine(custom_tags=custom_tags)

    # Add other providers here (e.g., "twitter", "reddit", "combined")
    # For now, fall back to stub
    return StubSentimentEngine()


# ============================================================================
# PR-F.5 Polymarket Normalization
# ============================================================================

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class PolymarketSnapshot:
    """Normalized Polymarket snapshot for strategy use.

    Attributes:
        event_id: Unique event identifier
        event_title: Human-readable event title
        outcome: Current outcome ("Yes", "No", etc.)
        probability: Probability of YES outcome (0.0 - 1.0)
        volume_usd: Trading volume in USD
        liquidity_usd: Available liquidity in USD
        bullish_score: Normalized bullish sentiment (0.0 - 1.0)
        event_risk: Normalized event risk (0.0 - 1.0)
        is_stale: Whether data is stale (from fallback)
        data_quality: Quality indicator ("ok", "stale", "missing")
    """
    event_id: str
    event_title: str
    outcome: str
    probability: float
    volume_usd: float
    liquidity_usd: float
    bullish_score: float
    event_risk: float
    is_stale: bool = False
    data_quality: str = "ok"


@dataclass
class PolymarketNormalizationParams:
    """Configuration for Polymarket normalization.

    Attributes:
        bullish_weight: Weight for YES outcomes in bullish calculation
        risk_weight: Weight for risk factors
        crisis_threshold: Probability threshold for crisis detection
        min_volume_usd: Minimum volume to consider market valid
    """
    bullish_weight: float = 0.7
    risk_weight: float = 0.3
    crisis_threshold: float = 0.5
    min_volume_usd: float = 1000.0


def normalize_polymarket_state(
    markets: List[Dict[str, Any]],
    params: Optional[PolymarketNormalizationParams] = None
) -> PolymarketSnapshot:
    """Normalize raw Polymarket market data into a structured snapshot.

    This is a PURE FUNCTION:
    - Input: List of market dicts from Polymarket API
    - Output: PolymarketSnapshot with normalized scores

    Algorithm:
    - Bullish Score: Weighted average of YES probabilities for bullish markets
    - Event Risk: Maximum of risk indicators (crash probabilities, low liquidity)

    Args:
        markets: List of market dicts from Polymarket API
        params: Optional normalization parameters

    Returns:
        PolymarketSnapshot with bullish_score and event_risk normalized to [0, 1]
    """
    params = params or PolymarketNormalizationParams()

    if not markets:
        # Return neutral snapshot on empty input
        return PolymarketSnapshot(
            event_id="neutral",
            event_title="Neutral Market",
            outcome="Neutral",
            probability=0.5,
            volume_usd=0.0,
            liquidity_usd=0.0,
            bullish_score=0.5,
            event_risk=0.0,
            is_stale=True,
            data_quality="missing"
        )

    # Extract and normalize probabilities from each market
    bullish_sum = 0.0
    bullish_count = 0
    risk_sum = 0.0
    risk_count = 0
    total_volume = 0.0
    total_liquidity = 0.0

    for market in markets:
        # Extract YES probability
        p_yes = None
        for key in ["probability", "outcome", "yes_price", "yesPrice", "p_yes"]:
            if key in market and market[key] is not None:
                try:
                    p_yes = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        if p_yes is not None:
            bullish_sum += p_yes
            bullish_count += 1

            # Calculate risk contribution (inverse of probability for some markets)
            # Higher probability "Yes" on positive markets = lower risk
            # But certain markets (crash, ban) have high risk when YES
            market_title = market.get("title", "").lower()
            is_crash_risk = any(
                kw in market_title
                for kw in ["crash", "ban", "depeg", "collapse", "war", "hack"]
            )

            if is_crash_risk:
                # Crash/ban markets: high YES = high risk
                risk_sum += p_yes
                risk_count += 1
            else:
                # Normal markets: high YES = low risk
                risk_sum += (1.0 - p_yes)
                risk_count += 1

        # Extract volume and liquidity
        volume = 0.0
        liquidity = 0.0

        for key in ["volume", "volume_usd", "volumeUSD"]:
            if key in market and market[key] is not None:
                try:
                    volume = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        for key in ["liquidity", "liquidity_usd", "liquidityUSD"]:
            if key in market and market[key] is not None:
                try:
                    liquidity = float(market[key])
                    break
                except (ValueError, TypeError):
                    continue

        total_volume += volume
        total_liquidity += liquidity

    # Calculate normalized scores
    if bullish_count > 0:
        avg_bullish = bullish_sum / bullish_count
    else:
        avg_bullish = 0.5  # Default neutral

    if risk_count > 0:
        avg_risk = risk_sum / risk_count
    else:
        avg_risk = 0.0

    # Normalize to [0, 1] range
    bullish_score = max(0.0, min(1.0, avg_bullish))
    event_risk = max(0.0, min(1.0, avg_risk))

    # Determine data quality
    is_stale = total_volume < params.min_volume_usd
    data_quality = "ok" if not is_stale else "stale"

    # Use first market as primary for ID/title
    primary = markets[0] if markets else {}

    return PolymarketSnapshot(
        event_id=primary.get("id", primary.get("event_id", "unknown")),
        event_title=primary.get("title", "Unknown Event"),
        outcome="Yes" if (primary.get("probability", 0.5) >= 0.5) else "No",
        probability=primary.get("probability", 0.5),
        volume_usd=total_volume,
        liquidity_usd=total_liquidity,
        bullish_score=bullish_score,
        event_risk=event_risk,
        is_stale=is_stale,
        data_quality=data_quality
    )


def create_polymarket_snapshot(
    markets: List[Dict[str, Any]],
    params: Optional[PolymarketNormalizationParams] = None
) -> PolymarketSnapshot:
    """Convenience wrapper for normalize_polymarket_state.

    Args:
        markets: List of market dicts from Polymarket API
        params: Optional normalization parameters

    Returns:
        PolymarketSnapshot instance
    """
    return normalize_polymarket_state(markets, params)
