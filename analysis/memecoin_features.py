#!/usr/bin/env python3
"""
analysis/memecoin_features.py

Pure functions for computing memecoin-specific features based on launch data.

PR-ML.2

Features:
- time_since_launch_hours: hours since first pool listing [0.0, 720.0]
- launch_source_encoded: one-hot encoding of launch source [0.0, 3.0]
- deployer_reputation_score: normalized deployer success [-1.0, +1.0]
- social_mention_velocity: mentions/minute [0.0, 10.0]

All functions are pure (no side effects), deterministic, and handle missing data gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Type hints
MintAddr = str
WalletAddr = str
Timestamp = int


# Constants
DEFAULT_LAUNCH_HOURS_NEUTRAL = 360.0  # Midpoint of [0, 720]
DEFAULT_SOURCE_NEUTRAL = 1.0  # Midpoint of [0, 3]
DEFAULT_REPUTATION_NEUTRAL = 0.0  # Neutral reputation
DEFAULT_VELOCITY_NEUTRAL = 1.0  # Normal mention velocity

# Launch source encoding
LAUNCH_SOURCE_ENCODING = {
    "pump_fun": 0.0,
    "raydium_cpmm": 1.0,
    "meteora": 2.0,
    "unknown": 3.0,
}

# Max values for clamping
MAX_LAUNCH_HOURS = 720.0
MAX_VELOCITY = 10.0


@dataclass
class MemecoinLaunchData:
    """Memecoin launch information."""
    mint: MintAddr
    first_pool_ts: Optional[Timestamp]  # milliseconds
    first_pool_source: Optional[str]  # "pump_fun", "raydium_cpmm", "meteora", "unknown"
    deployer_address: Optional[WalletAddr]
    deployer_reputation: Optional[float]  # [-1.0, +1.0]


@dataclass
class SocialData:
    """Social mention data for velocity computation."""
    mention_count: int
    time_window_minutes: int  # Window used for count


@dataclass
class MemecoinFeatures:
    """Container for computed memecoin features."""
    time_since_launch_hours: float = DEFAULT_LAUNCH_HOURS_NEUTRAL
    launch_source_encoded: float = DEFAULT_SOURCE_NEUTRAL
    deployer_reputation_score: float = DEFAULT_REPUTATION_NEUTRAL
    social_mention_velocity: float = DEFAULT_VELOCITY_NEUTRAL
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "time_since_launch_hours": self.time_since_launch_hours,
            "launch_source_encoded": self.launch_source_encoded,
            "deployer_reputation_score": self.deployer_reputation_score,
            "social_mention_velocity": self.social_mention_velocity,
        }


def compute_time_since_launch_hours(
    current_ts: Timestamp,
    first_pool_ts: Optional[Timestamp],
) -> float:
    """
    Compute hours since token launch (first pool creation).
    
    Args:
        current_ts: Current timestamp in milliseconds
        first_pool_ts: First pool creation timestamp in milliseconds
    
    Returns:
        Hours since launch [0.0, 720.0], defaults to 360.0 if unknown
    """
    if first_pool_ts is None or first_pool_ts <= 0:
        return DEFAULT_LAUNCH_HOURS_NEUTRAL
    
    hours_since = (current_ts - first_pool_ts) / (1000 * 60 * 60)
    
    # Clamp to valid range [0, 720]
    return max(0.0, min(MAX_LAUNCH_HOURS, hours_since))


def compute_launch_source_encoded(
    source: Optional[str],
) -> float:
    """
    Encode launch source as one-hot-like float value.
    
    Mapping:
        "pump_fun" -> 0.0
        "raydium_cpmm" -> 1.0
        "meteora" -> 2.0
        "unknown" -> 3.0
    
    Args:
        source: Launch source identifier
    
    Returns:
        Encoded value [0.0, 3.0], defaults to 1.0 (raydium_cpmm) if unknown
    """
    if source is None:
        return DEFAULT_SOURCE_NEUTRAL
    
    return LAUNCH_SOURCE_ENCODING.get(source.lower().strip(), DEFAULT_SOURCE_NEUTRAL)


def compute_deployer_reputation_score(
    reputation: Optional[float],
) -> float:
    """
    Get normalized deployer reputation score.
    
    Args:
        reputation: Raw reputation score [-1.0, +1.0] or None
    
    Returns:
        Reputation score [-1.0, +1.0], defaults to 0.0 if unknown
    """
    if reputation is None:
        return DEFAULT_REPUTATION_NEUTRAL
    
    # Clamp to valid range
    return max(-1.0, min(1.0, reputation))


def compute_social_mention_velocity(
    mention_count: int,
    time_window_minutes: int,
) -> float:
    """
    Compute social mention velocity (mentions per minute).
    
    Args:
        mention_count: Number of mentions in window
        time_window_minutes: Duration of window in minutes
    
    Returns:
        Mentions per minute [0.0, 10.0], defaults to 1.0 if no data
    """
    if time_window_minutes <= 0 or mention_count < 0:
        return DEFAULT_VELOCITY_NEUTRAL
    
    velocity = mention_count / time_window_minutes
    
    # Clamp to valid range [0, 10]
    return max(0.0, min(MAX_VELOCITY, velocity))


def compute_memecoin_features(
    current_ts: Timestamp,
    launch_data: MemecoinLaunchData,
    social_data: Optional[SocialData] = None,
) -> MemecoinFeatures:
    """
    Compute all memecoin features in one call.
    
    Args:
        current_ts: Current timestamp in milliseconds
        launch_data: Memecoin launch information
        social_data: Optional social mention data
    
    Returns:
        MemecoinFeatures with all computed values
    """
    features = MemecoinFeatures()
    
    # time_since_launch_hours
    features.time_since_launch_hours = compute_time_since_launch_hours(
        current_ts,
        launch_data.first_pool_ts,
    )
    
    # launch_source_encoded
    features.launch_source_encoded = compute_launch_source_encoded(
        launch_data.first_pool_source,
    )
    
    # deployer_reputation_score
    features.deployer_reputation_score = compute_deployer_reputation_score(
        launch_data.deployer_reputation,
    )
    
    # social_mention_velocity
    if social_data is not None:
        features.social_mention_velocity = compute_social_mention_velocity(
            social_data.mention_count,
            social_data.time_window_minutes,
        )
    
    return features


def main():
    """CLI for testing memecoin features."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Compute memecoin features")
    parser.add_argument("--current-ts", type=int, required=True, help="Current timestamp (ms)")
    parser.add_argument("--mint", required=True, help="Token mint address")
    parser.add_argument("--first-pool-ts", type=int, help="First pool timestamp (ms)")
    parser.add_argument("--source", help="Launch source (pump_fun, raydium_cpmm, meteora, unknown)")
    parser.add_argument("--deployer", help="Deployer address")
    parser.add_argument("--reputation", type=float, help="Deployer reputation score")
    parser.add_argument("--mentions", type=int, default=0, help="Mention count")
    parser.add_argument("--window-minutes", type=int, default=60, help="Time window in minutes")
    parser.add_argument("--summary-json", action="store_true", help="Print JSON to stdout")
    
    args = parser.parse_args()
    
    launch_data = MemecoinLaunchData(
        mint=args.mint,
        first_pool_ts=args.first_pool_ts,
        first_pool_source=args.source,
        deployer_address=args.deployer,
        deployer_reputation=args.reputation,
    )
    
    social_data = SocialData(
        mention_count=args.mentions,
        time_window_minutes=args.window_minutes,
    )
    
    features = compute_memecoin_features(
        args.current_ts,
        launch_data,
        social_data,
    )
    
    if args.summary_json:
        print(json.dumps(features.to_dict()))
    else:
        print(f"[memecoin] time_since_launch_hours={features.time_since_launch_hours:.1f}")
        print(f"[memecoin] launch_source_encoded={features.launch_source_encoded:.1f}")
        print(f"[memecoin] deployer_reputation_score={features.deployer_reputation_score:.2f}")
        print(f"[memecoin] social_mention_velocity={features.social_mention_velocity:.2f}")


if __name__ == "__main__":
    main()
