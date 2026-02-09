#!/usr/bin/env python3
"""
analysis/survival_model.py

Survival Analysis Model for Token Crash Prediction.

PR-ML.4

Computes hazard scores based on on-chain and market indicators
to predict token crash probability. Pure functions with no side effects.

Formula:
    hazard_raw = sigmoid(w · features)
    hazard_calibrated = interpolate(hazard_raw, calibration_curve)

Emergency Exit Trigger:
    if hazard_calibrated >= hazard_threshold: trigger_exit()
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default feature weights
DEFAULT_WEIGHTS = {
    "liquidity_drop_10s": 3.2,
    "top_holder_sell_ratio": 2.8,
    "mint_auth_exists": 1.5,
    "cluster_sell_pressure": 2.1,
    "pmkt_event_risk": 1.0,
}

# Sigmoid parameters
DEFAULT_SIGMOID_K = 10.0
DEFAULT_SIGMOID_X0 = 0.5

# Default calibration curve (raw -> calibrated)
DEFAULT_CALIBRATION_CURVE: List[Tuple[float, float]] = [
    (0.0, 0.0),
    (0.2, 0.15),
    (0.4, 0.35),
    (0.6, 0.65),
    (0.8, 0.85),
    (1.0, 1.0),
]

# Default hazard threshold for emergency exit
DEFAULT_HAZARD_THRESHOLD = 0.65


def sigmoid(x: float, k: float = DEFAULT_SIGMOID_K, x0: float = DEFAULT_SIGMOID_X0) -> float:
    """
    Sigmoid transformation with configurable steepness and midpoint.
    
    Args:
        x: Input value
        k: Steepness parameter (higher = steeper)
        x0: Midpoint parameter
        
    Returns:
        Value in (0.0, 1.0)
    """
    return 1.0 / (1.0 + __import__("math").exp(-k * (x - x0)))


def compute_hazard_score(
    features: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
    sigmoid_k: float = DEFAULT_SIGMOID_K,
    sigmoid_x0: float = DEFAULT_SIGMOID_X0,
) -> float:
    """
    Compute raw hazard score from features using weighted sum + sigmoid.
    
    Args:
        features: Dict with keys:
            - liquidity_drop_10s: % of liquidity lost in first 10s [0.0, 1.0]
            - top_holder_sell_ratio: % of top holders selling [0.0, 1.0]
            - mint_auth_exists: Whether mint authority exists {0.0, 1.0}
            - cluster_sell_pressure: Smart money cluster sell pressure [0.0, 1.0]
            - pmkt_event_risk: Polymarket event risk [0.0, 1.0]
        weights: Optional custom feature weights (uses defaults if None)
        sigmoid_k: Sigmoid steepness parameter
        sigmoid_x0: Sigmoid midpoint parameter
        
    Returns:
        Raw hazard score in [0.0, 1.0]
        
    Examples:
        >>> features = {
        ...     "liquidity_drop_10s": 0.92,
        ...     "top_holder_sell_ratio": 0.85,
        ...     "mint_auth_exists": 1.0,
        ...     "cluster_sell_pressure": 0.78,
        ...     "pmkt_event_risk": 0.45,
        ... }
        >>> score = compute_hazard_score(features)
        >>> 0.7 < score < 1.0  # Should be high for crash indicators
        True
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS.copy()
    
    # Validate required features
    required_keys = {"liquidity_drop_10s", "top_holder_sell_ratio", "mint_auth_exists", 
                     "cluster_sell_pressure", "pmkt_event_risk"}
    missing = required_keys - set(features.keys())
    if missing:
        raise ValueError(f"Missing required features: {missing}")
    
    # Compute weighted sum
    weighted_sum = sum(
        weights.get(key, 0.0) * features[key]
        for key in required_keys
    )
    
    # Apply sigmoid transformation
    # Normalize by sum of weights to keep input in reasonable range
    weight_sum = sum(weights.get(key, 0.0) for key in required_keys)
    normalized_input = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    
    return sigmoid(normalized_input, k=sigmoid_k, x0=sigmoid_x0)


def is_emergency_exit(
    hazard_score: float,
    hazard_threshold: float = DEFAULT_HAZARD_THRESHOLD,
) -> bool:
    """
    Determine if emergency exit should be triggered.
    
    Args:
        hazard_score: Calibrated hazard score [0.0, 1.0]
        hazard_threshold: Threshold for emergency exit (default: 0.65)
        
    Returns:
        True if emergency exit should be triggered
        
    Examples:
        >>> is_emergency_exit(0.80)
        True
        >>> is_emergency_exit(0.50)
        False
    """
    assert 0.0 <= hazard_score <= 1.0, f"hazard_score {hazard_score} out of bounds [0.0, 1.0]"
    assert 0.0 <= hazard_threshold <= 1.0, f"hazard_threshold {hazard_threshold} out of bounds [0.0, 1.0]"
    return hazard_score >= hazard_threshold


def calibrate_hazard_score(
    raw_score: float,
    calibration_curve: Optional[List[Tuple[float, float]]] = None,
) -> float:
    """
    Calibrate raw hazard score using calibration curve.
    
    Uses linear interpolation between calibration points.
    
    Args:
        raw_score: Raw hazard score from compute_hazard_score()
        calibration_curve: List of (raw, calibrated) tuples (uses default if None)
        
    Returns:
        Calibrated probability in [0.0, 1.0]
        
    Examples:
        >>> calibrate_hazard_score(0.5)
        0.50
        >>> calibrate_hazard_score(0.2)
        0.15
    """
    assert 0.0 <= raw_score <= 1.0, f"raw_score {raw_score} out of bounds [0.0, 1.0]"
    
    if calibration_curve is None:
        calibration_curve = DEFAULT_CALIBRATION_CURVE
    
    # Sort calibration points by raw score
    sorted_curve = sorted(calibration_curve, key=lambda x: x[0])
    
    # Handle edge cases
    if raw_score <= sorted_curve[0][0]:
        return sorted_curve[0][1]
    if raw_score >= sorted_curve[-1][0]:
        return sorted_curve[-1][1]
    
    # Find surrounding points for interpolation
    for i in range(len(sorted_curve) - 1):
        x0, y0 = sorted_curve[i]
        x1, y1 = sorted_curve[i + 1]
        if x0 <= raw_score <= x1:
            # Linear interpolation
            ratio = (raw_score - x0) / (x1 - x0) if (x1 - x0) > 0 else 0.0
            return y0 + ratio * (y1 - y0)
    
    # Fallback (shouldn't reach here)
    return raw_score


def compute_full_hazard(
    features: Dict[str, float],
    hazard_threshold: float = DEFAULT_HAZARD_THRESHOLD,
    calibration_curve: Optional[List[Tuple[float, float]]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """
    Compute complete hazard analysis with all outputs.
    
    Args:
        features: Feature dictionary
        hazard_threshold: Emergency exit threshold
        calibration_curve: Custom calibration curve
        weights: Custom feature weights
        
    Returns:
        Dict with:
            - hazard_score_raw: Raw score
            - hazard_score_calibrated: Calibrated probability
            - is_emergency_exit: Whether to trigger exit
            - triggering_features: List of features above threshold
            - model_version: Model identifier
    """
    raw_score = compute_hazard_score(features, weights=weights)
    calibrated_score = calibrate_hazard_score(raw_score, calibration_curve)
    emergency_exit = is_emergency_exit(calibrated_score, hazard_threshold)
    
    # Identify triggering features (those significantly above mean)
    triggering_features = []
    feature_mean = sum(features.values()) / len(features)
    for key, value in features.items():
        if value > 0.5 and value > feature_mean:
            triggering_features.append(key)
    
    return {
        "hazard_score_raw": round(raw_score, 4),
        "hazard_score_calibrated": round(calibrated_score, 4),
        "is_emergency_exit": emergency_exit,
        "triggering_features": triggering_features,
        "model_version": "hazard_v1",
    }


def get_triggering_features(
    features: Dict[str, float],
    threshold: float = 0.5,
) -> List[str]:
    """
    Identify features above threshold.
    
    Args:
        features: Feature dictionary
        threshold: Minimum value to be considered triggering
        
    Returns:
        List of feature names above threshold
    """
    return [key for key, value in features.items() if value >= threshold]


def main():
    """CLI for hazard model testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Survival Analysis Model CLI")
    parser.add_argument("--score", action="store_true", help="Compute hazard score")
    parser.add_argument("--calibrate", action="store_true", help="Show calibration curve")
    parser.add_argument("--test", action="store_true", help="Run test cases")
    
    args = parser.parse_args()
    
    if args.score:
        # Example features
        features = {
            "liquidity_drop_10s": 0.92,
            "top_holder_sell_ratio": 0.85,
            "mint_auth_exists": 1.0,
            "cluster_sell_pressure": 0.78,
            "pmkt_event_risk": 0.45,
        }
        result = compute_full_hazard(features)
        print(json.dumps(result, indent=2))
    
    if args.calibrate:
        print("Calibration curve:")
        for raw, calibrated in DEFAULT_CALIBRATION_CURVE:
            print(f"  raw={raw:.1f} -> calibrated={calibrated:.2f}")
    
    if args.test:
        # Run test cases
        crash_features = {
            "liquidity_drop_10s": 0.92,
            "top_holder_sell_ratio": 0.85,
            "mint_auth_exists": 1.0,
            "cluster_sell_pressure": 0.78,
            "pmkt_event_risk": 0.45,
        }
        
        survivor_features = {
            "liquidity_drop_10s": 0.05,
            "top_holder_sell_ratio": 0.08,
            "mint_auth_exists": 0.0,
            "cluster_sell_pressure": 0.05,
            "pmkt_event_risk": 0.10,
        }
        
        crash_score = compute_hazard_score(crash_features)
        survivor_score = compute_hazard_score(survivor_features)
        
        print(f"Crash score: {crash_score:.3f} (emergency_exit={is_emergency_exit(crash_score)})")
        print(f"Survivor score: {survivor_score:.3f} (emergency_exit={is_emergency_exit(survivor_score)})")
        
        assert crash_score > survivor_score, "Crash score should be higher"
        assert is_emergency_exit(crash_score), "Crash should trigger emergency exit"
        assert not is_emergency_exit(survivor_score), "Survivor should not trigger emergency exit"
        
        print("[survival_model] All tests passed!")


if __name__ == "__main__":
    main()
