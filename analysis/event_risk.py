"""
PR-PM.3 Event Risk Aggregator

Pure functions for detecting high-risk calendar events from Polymarket snapshots.
Event types: election, etf, regulatory, fed, macro, other
High risk = critical_type AND days_to_resolution <= 7 AND days_to_resolution >= 0
"""

import re
from dataclasses import dataclass
from typing import List


# Event type classification order: critical types first, then non-critical
# Note: "etf" comes before "regulatory" because ETF-specific keywords should take precedence
EVENT_TYPE_ORDER = ["election", "etf", "regulatory", "fed", "macro", "other"]
CRITICAL_TYPES = {"election", "etf", "regulatory"}

# Keyword patterns for each event type (case-insensitive, word boundaries)
EVENT_TYPE_PATTERNS = {
    "election": r"\b(election|vote|president|trump|harris|ballot)\b",
    "etf": r"\b(etf|spot\s+etf|bitcoin\s+etf|ethereum\s+etf|approve\s+etf)\b",
    "regulatory": r"\b(sec|regulation|ban|approve|reject|lawsuit|compliance)\b",
    "fed": r"\b(fed|fomc|interest\s+rate|powell|monetary\s+policy)\b",
    "macro": r"\b(recession|inflation|gdp|unemployment)\b",
}


@dataclass
class EventRiskTimeline:
    """Output schema for event risk aggregation."""
    ts: int
    high_event_risk: bool
    days_to_resolution: int
    event_type: str
    event_name: str
    source_snapshot_id: str


def detect_event_type(question: str) -> str:
    """
    Detect event type from question string.
    
    Args:
        question: The Polymarket question string
        
    Returns:
        Event type string: election, etf, regulatory, fed, macro, or other
    """
    question_lower = question.lower()
    
    for event_type in EVENT_TYPE_ORDER:
        pattern = EVENT_TYPE_PATTERNS.get(event_type)
        if pattern and re.search(pattern, question_lower, re.IGNORECASE):
            return event_type
    
    return "other"


def compute_days_to_resolution(event_date_unix_ms: int, now_ts_ms: int) -> int:
    """
    Calculate days from now until event resolution.
    
    Args:
        event_date_unix_ms: Event date in milliseconds since epoch
        now_ts_ms: Current timestamp in milliseconds
        
    Returns:
        Integer days (can be negative if event has passed)
    """
    delta_ms = event_date_unix_ms - now_ts_ms
    milliseconds_per_day = 24 * 3600 * 1000
    return int(delta_ms // milliseconds_per_day)


def truncate_event_name(question: str, max_length: int = 80) -> str:
    """
    Truncate event name to specified max length.
    
    Args:
        question: Original question string
        max_length: Maximum length for truncated name
        
    Returns:
        Truncated question string
    """
    return question[:max_length] if len(question) > max_length else question


@dataclass
class PolymarketSnapshotInput:
    """Input snapshot data for event risk detection."""
    market_id: str
    question: str
    event_date: int  # Unix milliseconds


def detect_event_risk(
    snapshots: List[PolymarketSnapshotInput],
    now_ts_ms: int
) -> EventRiskTimeline:
    """
    Detect high-risk events from Polymarket snapshots.
    
    Args:
        snapshots: List of Polymarket snapshots with questions and dates
        now_ts_ms: Reference timestamp in milliseconds
        
    Returns:
        EventRiskTimeline with aggregated event risk data
    """
    if not snapshots:
        # No snapshots - return empty/default result
        return EventRiskTimeline(
            ts=now_ts_ms,
            high_event_risk=False,
            days_to_resolution=0,
            event_type="other",
            event_name="",
            source_snapshot_id=""
        )
    
    # Filter and process each snapshot
    valid_events = []
    
    for snapshot in snapshots:
        # Skip markets without valid event dates
        if snapshot.event_date <= 0:
            continue
        
        event_type = detect_event_type(snapshot.question)
        days = compute_days_to_resolution(snapshot.event_date, now_ts_ms)
        
        valid_events.append({
            "snapshot": snapshot,
            "event_type": event_type,
            "days": days,
            "abs_days": abs(days),
            "is_critical": event_type in CRITICAL_TYPES,
        })
    
    if not valid_events:
        # No valid events found
        return EventRiskTimeline(
            ts=now_ts_ms,
            high_event_risk=False,
            days_to_resolution=0,
            event_type="other",
            event_name="",
            source_snapshot_id=""
        )
    
    # Aggregate: select event with minimal abs(days_to_resolution)
    # This picks the closest upcoming OR recently passed event
    closest_event = min(valid_events, key=lambda x: x["abs_days"])
    
    snapshot = closest_event["snapshot"]
    event_type = closest_event["event_type"]
    days = closest_event["days"]
    is_critical = closest_event["is_critical"]
    
    # High risk: critical type AND within 7 days AND not already passed
    high_event_risk = is_critical and 0 <= days <= 7
    
    return EventRiskTimeline(
        ts=now_ts_ms,
        high_event_risk=high_event_risk,
        days_to_resolution=days,
        event_type=event_type,
        event_name=truncate_event_name(snapshot.question),
        source_snapshot_id=snapshot.market_id
    )
