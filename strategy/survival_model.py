"""strategy/survival_model.py

Offline-trained survival model for predicting token crash probability within 60 seconds.

The model predicts P(exit_next_60s) using a logistic regression on features:
- volume_spike_15s_z: z-score of 15s volume relative to 5m average
- smart_money_exits_30s: number of Tier-1 wallet exits in 30s
- liquidity_drain_60s_pct: pool liquidity drain percentage over 60s
- price_impact_15s_bps: price impact in basis points over 15s

Coefficients are fixed and loaded from survival_coefficients.json (offline training only).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Default coefficients file (relative to this module)
COEFFICIENTS_FILE = Path(__file__).parent / "survival_coefficients.json"

# Rejection reason for invalid features
REJECT_HAZARD_FEATURES_INVALID = "hazard_features_invalid"

# Feature validation ranges
FEATURE_RANGES = {
    "volume_spike_15s_z": (-3.0, 5.0),
    "smart_money_exits_30s": (0, 10),
    "liquidity_drain_60s_pct": (-50.0, 10.0),
    "price_impact_15s_bps": (-500, 2000),
}

# Default coefficients (loaded from file in production)
DEFAULT_COEFFICIENTS = {
    "beta0": -1.2,
    "beta1": 0.35,
    "beta2": 0.8,
    "beta3": 0.04,
    "beta4": 0.0015,
}


def load_fixed_coefficients(path: Optional[str] = None) -> Dict[str, float]:
    """Load fixed model coefficients from JSON file.
    
    Args:
        path: Optional path to coefficients file. If None, uses default path.
    
    Returns:
        Dictionary with coefficients {beta0, beta1, beta2, beta3, beta4}.
    
    Raises:
        FileNotFoundError: If coefficients file doesn't exist.
        ValueError: If coefficients are invalid.
    """
    coef_path = Path(path) if path else COEFFICIENTS_FILE
    
    if not coef_path.exists():
        # Fallback to default coefficients
        return DEFAULT_COEFFICIENTS.copy()
    
    with open(coef_path, "r", encoding="utf-8") as f:
        coefficients = json.load(f)
    
    # Validate required coefficients
    required = ["beta0", "beta1", "beta2", "beta3", "beta4"]
    for coef in required:
        if coef not in coefficients:
            raise ValueError(f"Missing required coefficient: {coef}")
    
    return coefficients


def validate_features(features: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate that all required features are within expected ranges.
    
    Args:
        features: Dictionary with feature names and values.
    
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str]).
        If invalid, returns (False, REJECT_HAZARD_FEATURES_INVALID).
    """
    for feature_name, (min_val, max_val) in FEATURE_RANGES.items():
        if feature_name not in features:
            return False, f"Missing required feature: {feature_name}"
        
        value = features[feature_name]
        try:
            value = float(value)
        except (ValueError, TypeError):
            return False, f"Invalid value for {feature_name}: {value}"
        
        if value < min_val or value > max_val:
            return False, f"Feature {feature_name} out of range [{min_val}, {max_val}]: {value}"
    
    return True, None


def predict_exit_hazard(
    features: Dict[str, Any],
    coefficients: Optional[Dict[str, float]] = None
) -> Tuple[float, Optional[str]]:
    """Predict the probability of token exit within 60 seconds.
    
    Args:
        features: Dictionary with required features:
            - volume_spike_15s_z: z-score of 15s volume
            - smart_money_exits_30s: number of Tier-1 exits
            - liquidity_drain_60s_pct: liquidity drain percentage
            - price_impact_15s_bps: price impact in bps
        coefficients: Optional coefficients dict. If None, loads from file.
    
    Returns:
        Tuple of (hazard_score: float, error_message: Optional[str]).
        - hazard_score: Probability in [0.0, 1.0]
        - error_message: None on success, or rejection reason on failure.
    """
    # Validate features first
    is_valid, error = validate_features(features)
    if not is_valid:
        # Return neutral hazard_score (0.5) on validation failure
        return 0.5, error or REJECT_HAZARD_FEATURES_INVALID
    
    # Load coefficients if not provided
    if coefficients is None:
        try:
            coefficients = load_fixed_coefficients()
        except (FileNotFoundError, ValueError):
            coefficients = DEFAULT_COEFFICIENTS.copy()
    
    # Extract features (validated, so safe to use)
    volume_spike = float(features["volume_spike_15s_z"])
    smart_money_exits = float(features["smart_money_exits_30s"])
    liquidity_drain = float(features["liquidity_drain_60s_pct"])
    price_impact = float(features["price_impact_15s_bps"])
    
    # Calculate logit
    logit = (
        coefficients["beta0"]
        + coefficients["beta1"] * volume_spike
        + coefficients["beta2"] * smart_money_exits
        + coefficients["beta3"] * liquidity_drain
        + coefficients["beta4"] * price_impact
    )
    
    # Apply sigmoid to get probability
    hazard_score = 1.0 / (1.0 + __import__("math").exp(-logit))
    
    # Clamp to [0.0, 1.0] for safety
    hazard_score = max(0.0, min(1.0, hazard_score))
    
    return hazard_score, None
