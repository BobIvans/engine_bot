"""strategy/sentiment.py

Sentiment analysis utilities including Polymarket normalization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class PolymarketSnapshot:
    """Canonical Polymarket snapshot record."""
    ts: int  # Snapshot timestamp in milliseconds
    market_id: str
    question: str
    p_yes: float
    p_no: float
    volume_usd: float
    event_date: int  # Event expiration in milliseconds
    category_tags: List[str]


def normalize_polymarket_market(raw: dict, snapshot_ts: int) -> PolymarketSnapshot:
    """Normalize raw Polymarket API response to canonical format.
    
    Args:
        raw: Raw market data from Gamma API.
        snapshot_ts: Snapshot timestamp in milliseconds.
    
    Returns:
        PolymarketSnapshot with normalized fields.
    
    Raises:
        ValueError: If required fields are missing or validation fails.
    """
    # Extract required fields
    market_id = raw.get("id")
    if not market_id:
        raise ValueError("Missing required field: id")
    
    question = raw.get("question", "")
    if not question:
        raise ValueError("Missing required field: question")
    
    # Extract price1 (assumed to be YES outcome)
    price1 = raw.get("price1")
    if price1 is None:
        raise ValueError("Missing required field: price1")
    
    try:
        p_yes = float(price1)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid price1 value: {price1}")
    
    # Calculate p_no (1 - p_yes)
    p_no = 1.0 - p_yes
    
    # Validate probability sum (allow small rounding tolerance)
    if abs(p_yes + p_no - 1.0) > 0.01:
        raise ValueError(f"Probability validation failed: p_yes={p_yes}, p_no={p_no}")
    
    # Extract volume
    volume_usd_raw = raw.get("volumeUSD")
    if volume_usd_raw is None:
        raise ValueError("Missing required field: volumeUSD")
    
    try:
        volume_usd = float(volume_usd_raw)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid volumeUSD value: {volume_usd_raw}")
    
    # Extract event expiration date
    event_date_raw = raw.get("eventExpirationDate")
    if not event_date_raw:
        raise ValueError("Missing required field: eventExpirationDate")
    
    # Parse ISO timestamp to milliseconds
    try:
        # Handle ISO format with Z suffix
        event_dt = datetime.fromisoformat(
            event_date_raw.replace("Z", "+00:00")
        )
        event_date = int(event_dt.timestamp() * 1000)
    except ValueError:
        raise ValueError(f"Invalid eventExpirationDate format: {event_date_raw}")
    
    # Categorize based on question keywords
    category_tags = _categorize_question(question)
    
    return PolymarketSnapshot(
        ts=snapshot_ts,
        market_id=market_id,
        question=question,
        p_yes=p_yes,
        p_no=p_no,
        volume_usd=volume_usd,
        event_date=event_date,
        category_tags=category_tags,
    )


def _categorize_question(question: str) -> List[str]:
    """Categorize a market based on keywords in the question.
    
    Args:
        question: Market question text.
    
    Returns:
        List of category tags.
    """
    tags: List[str] = []
    question_lower = question.lower()
    
    # Crypto categories
    if "bitcoin" in question_lower or "btc" in question_lower:
        tags.extend(["crypto", "bitcoin"])
    elif "ethereum" in question_lower or "eth" in question_lower:
        tags.extend(["crypto", "ethereum"])
    elif "solana" in question_lower or "sol" in question_lower:
        tags.extend(["crypto", "solana"])
    else:
        # Default crypto tag if crypto mentioned but not specific coin
        if "crypto" in question_lower:
            tags.append("crypto")
    
    # Politics categories
    if "trump" in question_lower:
        tags.extend(["politics", "us_election"])
    elif "harris" in question_lower:
        tags.extend(["politics", "us_election"])
    elif "election" in question_lower or "president" in question_lower:
        tags.append("politics")
    
    # Finance categories
    if "sp 500" in question_lower or "s&p" in question_lower:
        tags.append("finance")
    elif "inflation" in question_lower:
        tags.append("economics")
    elif "gdp" in question_lower:
        tags.append("economics")
    
    # Sports categories
    if "super bowl" in question_lower:
        tags.append("sports")
    elif "olympic" in question_lower:
        tags.append("sports")
    elif "world cup" in question_lower:
        tags.append("sports")
    
    # Default tag if no categories matched
    if not tags:
        tags.append("general")
    
    return tags
