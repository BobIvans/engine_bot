"""
Survival Analysis Model - Exit Hazard Estimation

Computes hazard_score - instant probability of position "death" (price crash)
in the near window. Used for L_aggr mode where holding is limited by
growing risk rather than fixed time.

Pure logic module. Input: features (dict), params (dict). Output: hazard_score (float).
"""

import json
import math
from pathlib import Path
from typing import Dict, Optional


# Default weights for MVP
DEFAULT_WEIGHTS = {
    "baseline_hazard": 0.1,
    "time_decay_factor": 0.001,
    "weights": {
        "smart_money_exit_count": 0.5,
        "volatility_z_score": 0.2,
        "volume_delta_pct": 0.1
    }
}


class SurvivalEstimator:
    """
    Survival Analysis Estimator using simplified Cox Proportional Hazards.
    
    Hazard Score Formula (simplified):
    hazard(t|x) = baseline_hazard * exp(sum(beta_i * x_i))
    
    Where:
    - baseline_hazard(t) = baseline_hazard + time_decay_factor * duration_sec
    - x_i are features (volatility_z_score, smart_money_exit_count, etc.)
    - beta_i are weights
    """
    
    def __init__(self, weights_path: Optional[str] = None, safety_mode: str = "safe_default"):
        """
        Initialize SurvivalEstimator with weights.
        
        Args:
            weights_path: Path to JSON weights file. If None, uses defaults.
            safety_mode: How to handle NaN values - "safe_default" (0.5) or "high_risk" (1.0)
        """
        self.safety_mode = safety_mode
        self.weights = self._load_weights(weights_path)
    
    def _load_weights(self, weights_path: Optional[str]) -> Dict:
        """Load weights from JSON file or use defaults."""
        if weights_path is None:
            return DEFAULT_WEIGHTS.copy()
        
        weights_file = Path(weights_path)
        if weights_file.exists():
            with open(weights_file, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults for any missing keys
                result = DEFAULT_WEIGHTS.copy()
                result.update(loaded)
                return result
        return DEFAULT_WEIGHTS.copy()
    
    def _get_feature_value(self, features: Dict, key: str) -> float:
        """Safely get feature value, return 0 if missing."""
        return float(features.get(key, 0.0))
    
    def _check_nan(self, value: float) -> bool:
        """Check if value is NaN."""
        return math.isnan(value) or math.isinf(value)
    
    def predict_hazard(self, features: Dict, duration_sec: float) -> float:
        """
        Predict hazard score based on features and duration.
        
        Args:
            features: Dict with keys:
                - volatility_z_score: Z-score of price volatility
                - smart_money_exit_count: Number of smart money exits
                - volume_delta_pct: Volume change percentage
            duration_sec: Time since position opened (seconds)
        
        Returns:
            float: Hazard score in [0.0, 1.0] range
                   0.0 = safe (no risk)
                   1.0 = critical risk (guaranteed exit)
        """
        # Handle NaN in features with fail-safe
        for key in features:
            if self._check_nan(features[key]):
                if self.safety_mode == "high_risk":
                    return 1.0
                return 0.5  # safe_default
        
        # Extract feature values
        smart_money_exit = self._get_feature_value(features, "smart_money_exit_count")
        volatility = self._get_feature_value(features, "volatility_z_score")
        volume_delta = self._get_feature_value(features, "volume_delta_pct")
        
        # Calculate baseline hazard that grows with time
        baseline = self.weights["baseline_hazard"] + (
            self.weights["time_decay_factor"] * duration_sec
        )
        
        # Calculate linear predictor (sum of weighted features)
        w = self.weights["weights"]
        linear_predictor = (
            w["smart_money_exit_count"] * smart_money_exit +
            w["volatility_z_score"] * volatility +
            w.get("volume_delta_pct", 0.1) * volume_delta
        )
        
        # Cox model: hazard = baseline * exp(linear_predictor)
        raw_hazard = baseline * math.exp(linear_predictor)
        
        # Clamp to [0, 1] range
        clamped_hazard = max(0.0, min(1.0, raw_hazard))
        
        return clamped_hazard
    
    def should_exit(self, hazard_score: float, threshold: float = 0.7) -> bool:
        """
        Determine if position should be exited based on hazard score.
        
        Args:
            hazard_score: Predicted hazard score from predict_hazard()
            threshold: Exit threshold (default 0.7)
        
        Returns:
            bool: True if should exit, False if can hold
        """
        return hazard_score >= threshold
    
    def get_verdict(self, hazard_score: float, threshold: float = 0.7) -> str:
        """Get human-readable verdict for hazard score."""
        if hazard_score >= threshold:
            return "EXIT"
        return "HOLD"


# Convenience function for direct usage
def estimate_hazard(
    features: Dict,
    duration_sec: float,
    weights_path: Optional[str] = None,
    threshold: float = 0.7
) -> tuple:
    """
    Convenience function to estimate hazard and get exit decision.
    
    Returns:
        tuple: (hazard_score: float, should_exit: bool, verdict: str)
    """
    estimator = SurvivalEstimator(weights_path)
    hazard = estimator.predict_hazard(features, duration_sec)
    return (
        hazard,
        estimator.should_exit(hazard, threshold),
        estimator.get_verdict(hazard, threshold)
    )


def estimate_exit_probability_simple(
    median_hold_sec: Optional[float],
    window_sec: float = 60.0,
    default_prob: float = 0.5,
) -> float:
    """Estimate probability of exit within ``window_sec`` from median hold time.

    Backward-compatible helper for feature builders. Returns ``default_prob``
    when ``median_hold_sec`` is missing/invalid and clamps output to [0, 1].
    """

    def _clamp01(v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    try:
        default = _clamp01(float(default_prob))
    except Exception:
        default = 0.5

    if median_hold_sec is None:
        return default

    try:
        hold = float(median_hold_sec)
        window = float(window_sec)
    except Exception:
        return default

    if hold <= 0 or window <= 0:
        return default

    # Simple exponential survival model: P(exit by t) = 1 - exp(-t / median_hold)
    prob = 1.0 - math.exp(-window / hold)
    return _clamp01(prob)


if __name__ == "__main__":
    # Quick self-test
    print("Survival Estimator Self-Test")
    print("=" * 40)
    
    estimator = SurvivalEstimator()
    
    # Safe case: low volatility, no smart money exits, short duration
    safe_features = {
        "volatility_z_score": 0.5,
        "smart_money_exit_count": 0,
        "volume_delta_pct": -0.1
    }
    safe_hazard = estimator.predict_hazard(safe_features, 10.0)
    print(f"Safe case: Hazard={safe_hazard:.2f} -> {estimator.get_verdict(safe_hazard)}")
    
    # Danger case: high volatility, many smart money exits, long duration
    danger_features = {
        "volatility_z_score": 3.0,
        "smart_money_exit_count": 5,
        "volume_delta_pct": 2.0
    }
    danger_hazard = estimator.predict_hazard(danger_features, 300.0)
    print(f"Danger case: Hazard={danger_hazard:.2f} -> {estimator.get_verdict(danger_hazard)}")
