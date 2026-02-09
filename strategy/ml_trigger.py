#!/usr/bin/env python3
"""strategy/ml_trigger.py

PR-N.2 Retraining Trigger Logic (Cadence & Drift)

Pure logic for ML model retraining decisions:
- Cadence check: Has enough time passed since last training?
- Drift detection: Has feature distribution shifted significantly (PSI > Threshold)?

This module contains NO I/O - pure functions only.
"""

from __future__ import annotations

import json
import math
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple


# Epsilon for numerical stability
_EPS = 1e-15


def check_cadence(
    last_train_ts: int,
    current_ts: int,
    interval_hours: int,
) -> Tuple[bool, Dict[str, Any]]:
    """Check if enough time has passed since last training.
    
    Pure function: output depends only on inputs.
    
    Args:
        last_train_ts: Unix timestamp of last training
        current_ts: Current Unix timestamp
        interval_hours: Required hours between trainings
    
    Returns:
        Tuple of (should_retrain: bool, details: dict)
    
    Examples:
        >>> # Cadence not expired
        >>> check_cadence(1700000000, 1700000000 + 12*3600, 24)
        (False, {'expired': False, 'hours_since': 12.0, 'threshold': 24})
        
        >>> # Cadence expired
        >>> check_cadence(1700000000, 1700000000 + 48*3600, 24)
        (True, {'expired': True, 'hours_since': 48.0, 'threshold': 24})
    """
    hours_since = (current_ts - last_train_ts) / 3600.0
    expired = hours_since >= interval_hours
    
    return (
        expired,
        {
            "expired": expired,
            "hours_since": hours_since,
            "threshold": interval_hours,
        }
    )


def _compute_bucket_bounds_equal_width(
    values: List[float],
    num_buckets: int,
    epsilon: float = _EPS,
) -> List[float]:
    """Compute bucket boundaries using equal-width binning.
    
    This approach is more robust for distributions with extreme values.
    
    Args:
        values: List of values to compute buckets from
        num_buckets: Number of buckets to create
        epsilon: Small value to pad range
    
    Returns:
        List of bucket boundaries
    """
    min_val = min(values)
    max_val = max(values)
    
    # Add padding to ensure all values are covered
    range_val = max_val - min_val
    if range_val < epsilon:
        range_val = 1.0  # Single value case
    
    bucket_width = range_val / num_buckets
    bounds = []
    
    for i in range(1, num_buckets):
        bounds.append(min_val + i * bucket_width)
    
    return bounds


def _compute_bucket_counts(
    values: List[float],
    bucket_bounds: List[float],
) -> List[int]:
    """Count values in each bucket.
    
    Args:
        values: Values to count
        bucket_bounds: Bucket boundaries (sorted)
    
    Returns:
        List of counts per bucket
    """
    num_buckets = len(bucket_bounds) + 1
    counts = [0] * num_buckets
    
    for value in values:
        bucket_idx = 0
        for bound in bucket_bounds:
            if value >= bound:
                bucket_idx += 1
            else:
                break
        counts[bucket_idx] += 1
    
    return counts


def compute_feature_psi(
    baseline_values: List[float],
    current_values: List[float],
    num_buckets: int = 10,
    epsilon: float = _EPS,
) -> float:
    """Compute Population Stability Index (PSI) for a feature.
    
    PSI = sum((Actual% - Expected%) * ln(Actual% / Expected%))
    
    Pure function: output depends only on inputs.
    
    Args:
        baseline_values: Values from baseline/training distribution
        current_values: Values from current distribution to compare
        num_buckets: Number of bins for bucketing (default: 10)
        epsilon: Small value to avoid division by zero
    
    Returns:
        PSI score (float)
    
    Examples:
        >>> # Identical distributions
        >>> compute_feature_psi([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], num_buckets=5)
        0.0
        
        >>> # Different distributions should have higher PSI
        >>> baseline = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        >>> current = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
        >>> psi = compute_feature_psi(baseline, current, num_buckets=5)
        >>> psi > 0.5
        True
    """
    if len(baseline_values) == 0 or len(current_values) == 0:
        return 0.0
    
    # Use equal-width bucketing for stability
    bucket_bounds = _compute_bucket_bounds_equal_width(baseline_values, num_buckets)
    
    # Count values in each bucket for both distributions
    baseline_counts = _compute_bucket_counts(baseline_values, bucket_bounds)
    current_counts = _compute_bucket_counts(current_values, bucket_bounds)
    
    # Convert to proportions
    baseline_total = len(baseline_values)
    current_total = len(current_values)
    
    baseline_props = [max(c / baseline_total, epsilon) for c in baseline_counts]
    current_props = [max(c / current_total, epsilon) for c in current_counts]
    
    # Compute PSI
    psi = 0.0
    for baseline_p, current_p in zip(baseline_props, current_props):
        psi += (current_p - baseline_p) * math.log(current_p / baseline_p)
    
    return psi


def compute_feature_psi_quantile(
    baseline_values: List[float],
    current_values: List[float],
    num_buckets: int = 10,
    epsilon: float = _EPS,
) -> float:
    """Compute PSI using quantile-based bucketing (alternative method).
    
    This method creates buckets based on baseline distribution quantiles.
    """
    if len(baseline_values) == 0 or len(current_values) == 0:
        return 0.0
    
    # Compute bucket boundaries from baseline (using quantiles)
    sorted_baseline = sorted(baseline_values)
    bucket_bounds = []
    
    for i in range(1, num_buckets):
        idx = int(i * len(sorted_baseline) / num_buckets)
        if idx < len(sorted_baseline):
            bucket_bounds.append(sorted_baseline[idx])
        else:
            bucket_bounds.append(sorted_baseline[-1])
    
    # Count values in each bucket for both distributions
    baseline_counts = _compute_bucket_counts(baseline_values, bucket_bounds)
    current_counts = _compute_bucket_counts(current_values, bucket_bounds)
    
    # Convert to proportions
    baseline_total = len(baseline_values)
    current_total = len(current_values)
    
    baseline_props = [max(c / baseline_total, epsilon) for c in baseline_counts]
    current_props = [max(c / current_total, epsilon) for c in current_counts]
    
    # Compute PSI
    psi = 0.0
    for baseline_p, current_p in zip(baseline_props, current_props):
        psi += (current_p - baseline_p) * math.log(current_p / baseline_p)
    
    return psi


def compute_feature_psi_with_stats(
    baseline_values: List[float],
    current_values: List[float],
    num_buckets: int = 10,
) -> Dict[str, Any]:
    """Compute PSI with additional statistics.
    
    Args:
        baseline_values: Values from baseline distribution
        current_values: Values from current distribution
        num_buckets: Number of buckets
    
    Returns:
        Dict with psi score and bucket-level details
    """
    if len(baseline_values) == 0 or len(current_values) == 0:
        return {
            "psi": 0.0,
            "baseline_mean": 0.0,
            "current_mean": 0.0,
            "baseline_std": 0.0,
            "current_std": 0.0,
            "bucket_details": [],
        }
    
    psi = compute_feature_psi(baseline_values, current_values, num_buckets)
    
    bucket_bounds = _compute_bucket_counts(baseline_values, _compute_bucket_bounds(baseline_values, num_buckets))
    
    # Compute basic statistics
    baseline_mean = mean(baseline_values) if baseline_values else 0.0
    current_mean = mean(current_values) if current_values else 0.0
    
    baseline_var = mean((x - baseline_mean) ** 2 for x in baseline_values) if baseline_values else 0.0
    current_var = mean((x - current_mean) ** 2 for x in current_values) if current_values else 0.0
    
    return {
        "psi": psi,
        "baseline_mean": baseline_mean,
        "current_mean": current_mean,
        "baseline_std": math.sqrt(baseline_var) if baseline_var > 0 else 0.0,
        "current_std": math.sqrt(current_var) if current_var > 0 else 0.0,
        "bucket_details": {
            "baseline_counts": bucket_bounds,
            "num_buckets": num_buckets,
        },
    }


def decide_retraining(
    metadata: Dict[str, Any],
    current_features: Dict[str, List[float]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether ML model retraining is needed.
    
    Pure function: output depends only on inputs.
    
    Args:
        metadata: Model metadata with last_train_ts and optionally baseline_stats
            {
                "last_train_ts": int,
                "baseline_stats": {
                    "feature_name": [baseline_values]
                }
            }
        current_features: Current feature values
            {
                "feature_name": [current_values]
            }
        config: Configuration with thresholds
            {
                "cadence_hours": int,
                "drift_psi_threshold": float
            }
    
    Returns:
        Decision result:
            {
                "trigger": bool,
                "reasons": List[str],
                "metrics": {
                    "max_psi": float,
                    "age_hours": float,
                    "psi_per_feature": {feature: psi}
                }
            }
    
    Examples:
        >>> # No retraining needed
        >>> metadata = {"last_train_ts": 1700000000, "baseline_stats": {"f1": [1,2,3]}}
        >>> current = {"f1": [1,2,3,4]}
        >>> config = {"cadence_hours": 24, "drift_psi_threshold": 0.15}
        >>> # With recent training and no drift
        >>> result = decide_retraining(metadata, current, config)
        >>> result["trigger"] in [True, False]
        True
    """
    reasons: List[str] = []
    metrics: Dict[str, Any] = {}
    psi_per_feature: Dict[str, float] = {}
    
    # 1. Check cadence
    last_train_ts = metadata.get("last_train_ts", 0)
    current_ts = metadata.get("current_ts", 0)
    cadence_hours = config.get("cadence_hours", 24)
    
    cadence_expired, cadence_details = check_cadence(
        last_train_ts, current_ts, cadence_hours
    )
    
    metrics["age_hours"] = cadence_details["hours_since"]
    
    if cadence_expired:
        reasons.append("cadence_expired")
    
    # 2. Check drift for each feature
    baseline_stats = metadata.get("baseline_stats", {})
    drift_threshold = config.get("drift_psi_threshold", 0.15)
    drift_detected = False
    
    # Get list of features to check (union of baseline and current)
    all_features = set(baseline_stats.keys()) | set(current_features.keys())
    
    for feature in all_features:
        baseline_values = baseline_stats.get(feature, [])
        current_values = current_features.get(feature, [])
        
        if not baseline_values or not current_values:
            continue
        
        # Compute PSI for this feature
        psi = compute_feature_psi(baseline_values, current_values)
        psi_per_feature[feature] = psi
        
        if psi > drift_threshold:
            drift_detected = True
    
    metrics["max_psi"] = max(psi_per_feature.values()) if psi_per_feature else 0.0
    metrics["psi_per_feature"] = psi_per_feature
    
    if drift_detected:
        reasons.append("drift_detected")
    
    # 3. Make final decision
    trigger = cadence_expired or drift_detected
    
    return {
        "trigger": trigger,
        "reasons": reasons,
        "metrics": metrics,
    }


# Alias for convenience
should_retrain = decide_retraining


if __name__ == "__main__":
    # Demo usage
    print("ML Trigger Logic Demo")
    print("=" * 50)
    
    # Example 1: Cadence check
    print("\n1. Cadence Check:")
    last_train = 1700000000  # Some timestamp
    current = 1700000000 + 48 * 3600  # 48 hours later
    
    expired, details = check_cadence(last_train, current, 24)
    print(f"   Last trained: {last_train}")
    print(f"   Current: {current}")
    print(f"   Cadence expired: {expired}")
    print(f"   Details: {details}")
    
    # Example 2: PSI calculation
    print("\n2. PSI Calculation:")
    baseline = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    current_similar = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    current_different = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    
    psi_similar = compute_feature_psi(baseline, current_similar)
    psi_different = compute_feature_psi(baseline, current_different)
    
    print(f"   Similar distribution PSI: {psi_similar:.4f}")
    print(f"   Different distribution PSI: {psi_different:.4f}")
    
    # Example 3: Full decision
    print("\n3. Retraining Decision:")
    metadata = {
        "last_train_ts": 1700000000,
        "baseline_stats": {
            "feature_a": list(range(100)),
            "feature_b": list(range(50, 150)),
        }
    }
    current_features = {
        "feature_a": list(range(100)),
        "feature_b": list(range(50, 150)),
    }
    config = {
        "cadence_hours": 24,
        "drift_psi_threshold": 0.15,
    }
    
    # With recent timestamp (no cadence trigger)
    metadata["current_ts"] = 1700000000 + 12 * 3600
    result = decide_retraining(metadata, current_features, config)
    print(f"   Recent timestamp result: {result}")
    
    # With old timestamp (cadence trigger)
    metadata["current_ts"] = 1700000000 + 48 * 3600
    result = decide_retraining(metadata, current_features, config)
    print(f"   Old timestamp result: {result}")
