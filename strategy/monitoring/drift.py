"""
Pure logic for Feature Drift Detection.

Computes Population Stability Index (PSI) for feature distributions to detect
data drift between training (baseline) and production (current) samples.

PSI interpretation:
  - PSI < 0.1:  No significant drift
  - 0.1 <= PSI < 0.25: Moderate drift (monitor)
  - PSI >= 0.25: Significant drift (action required)

Output format: drift_report.v1.json
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import math


@dataclass
class DriftResult:
    """Drift analysis result for a single feature."""
    feature_name: str
    psi: float
    is_drifted: bool
    
    def to_dict(self) -> dict:
        return {
            "psi": round(self.psi, 4),
            "is_drifted": self.is_drifted,
        }


def calculate_psi(
    expected_dist: List[float],
    actual_dist: List[float],
    epsilon: float = 1e-10
) -> float:
    """
    Calculate Population Stability Index between two distributions.
    
    PSI = sum((Actual% - Expected%) * ln(Actual% / Expected%))
    
    Args:
        expected_dist: Expected proportions per bucket (must sum to ~1.0)
        actual_dist: Actual proportions per bucket (must sum to ~1.0)
        epsilon: Small value to prevent division by zero
        
    Returns:
        PSI score (non-negative float)
    """
    if len(expected_dist) != len(actual_dist):
        raise ValueError(
            f"Distribution lengths must match: {len(expected_dist)} vs {len(actual_dist)}"
        )
    
    if not expected_dist:
        return 0.0
    
    psi = 0.0
    for expected, actual in zip(expected_dist, actual_dist):
        # Apply epsilon to avoid log(0) and division by zero
        exp_safe = max(expected, epsilon)
        act_safe = max(actual, epsilon)
        
        # PSI formula for each bucket
        psi += (act_safe - exp_safe) * math.log(act_safe / exp_safe)
    
    return psi


def build_bucket_distribution(
    values: List[float],
    bucket_edges: List[float]
) -> List[float]:
    """
    Build bucket distribution (proportions) from raw values.
    
    Args:
        values: Raw feature values to bucket
        bucket_edges: Bucket boundaries [e0, e1, e2, ...] defining buckets
                      [e0,e1), [e1,e2), ..., [eN-1, eN]
                      
    Returns:
        List of proportions per bucket (sums to 1.0)
    """
    if len(bucket_edges) < 2:
        raise ValueError("Need at least 2 edges to define buckets")
    
    num_buckets = len(bucket_edges) - 1
    counts = [0] * num_buckets
    
    for value in values:
        # Find which bucket this value belongs to
        for i in range(num_buckets):
            left = bucket_edges[i]
            right = bucket_edges[i + 1]
            
            # Last bucket is inclusive on both ends [left, right]
            if i == num_buckets - 1:
                if left <= value <= right:
                    counts[i] += 1
                    break
            else:
                # [left, right)
                if left <= value < right:
                    counts[i] += 1
                    break
    
    total = sum(counts)
    if total == 0:
        # Return uniform distribution if no values matched
        return [1.0 / num_buckets] * num_buckets
    
    return [c / total for c in counts]


def counts_to_proportions(counts: List[int]) -> List[float]:
    """
    Convert bucket counts to proportions.
    
    Args:
        counts: Raw counts per bucket
        
    Returns:
        Proportions (sums to 1.0)
    """
    total = sum(counts)
    if total == 0:
        n = len(counts)
        return [1.0 / n] * n if n > 0 else []
    return [c / total for c in counts]


def analyze_drift(
    baseline_stats: Dict,
    current_features: List[Dict[str, float]],
    threshold: float = 0.25
) -> Tuple[Dict[str, DriftResult], str]:
    """
    Analyze drift for all monitored features.
    
    Args:
        baseline_stats: Baseline statistics with bucket definitions:
            {
                "monitored_features": ["feat1", "feat2"],
                "buckets": {
                    "feat1": {
                        "edges": [0, 2, 4, 6, 8, 10],
                        "expected_counts": [100, 100, 100, 100, 100]
                    }
                }
            }
        current_features: List of feature dictionaries from current batch
        threshold: PSI threshold for CRITICAL status
        
    Returns:
        Tuple of (feature_results dict, global_status string)
    """
    monitored = baseline_stats.get("monitored_features", [])
    buckets_config = baseline_stats.get("buckets", {})
    
    results: Dict[str, DriftResult] = {}
    max_psi = 0.0
    
    for feature_name in monitored:
        if feature_name not in buckets_config:
            continue
            
        config = buckets_config[feature_name]
        edges = config["edges"]
        expected_counts = config["expected_counts"]
        
        # Get expected distribution (proportions)
        expected_dist = counts_to_proportions(expected_counts)
        
        # Extract current feature values
        current_values = [
            row.get(feature_name, 0.0) 
            for row in current_features 
            if feature_name in row
        ]
        
        if not current_values:
            # No data for this feature - skip
            continue
        
        # Build actual distribution from current values
        actual_dist = build_bucket_distribution(current_values, edges)
        
        # Calculate PSI
        psi = calculate_psi(expected_dist, actual_dist)
        is_drifted = psi >= threshold
        
        results[feature_name] = DriftResult(
            feature_name=feature_name,
            psi=psi,
            is_drifted=is_drifted,
        )
        
        max_psi = max(max_psi, psi)
    
    # Determine global status
    if max_psi >= threshold:
        global_status = "CRITICAL"
    elif max_psi >= 0.1:
        global_status = "WARNING"
    else:
        global_status = "OK"
    
    return results, global_status


def format_output(
    results: Dict[str, DriftResult],
    global_status: str,
    threshold: float
) -> dict:
    """Format drift results for JSON output."""
    return {
        "version": "drift_report.v1",
        "threshold": threshold,
        "features": {
            name: result.psi
            for name, result in results.items()
        },
        "global_status": global_status,
    }


if __name__ == "__main__":
    # Simple test
    import json
    
    baseline = {
        "monitored_features": ["feature_A"],
        "buckets": {
            "feature_A": {
                "edges": [0, 2, 4, 6, 8, 10],
                "expected_counts": [100, 100, 100, 100, 100]  # Uniform
            }
        }
    }
    
    # Test 1: No drift (uniform distribution)
    current_normal = [{"feature_A": v} for v in range(0, 10)]
    results, status = analyze_drift(baseline, current_normal)
    print(f"Normal case: PSI={results['feature_A'].psi:.4f}, status={status}")
    
    # Test 2: Drift (all values in last bucket)
    current_drift = [{"feature_A": 9.5} for _ in range(100)]
    results, status = analyze_drift(baseline, current_drift)
    print(f"Drift case: PSI={results['feature_A'].psi:.4f}, status={status}")
