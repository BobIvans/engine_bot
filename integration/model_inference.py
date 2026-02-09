"""Model inference interface.

This repo is model-off first: the pipeline must run deterministically even when
no model artifact is available.

This module provides:
- SimpleLinearModel: A pure Python linear model for deterministic testing
- infer_p_model: Main inference function supporting "model_off" and "json_weights" modes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def sigmoid(z: float) -> float:
    """Sigmoid function for converting z-score to probability [0, 1]."""
    if z >= 0:
        return 1.0 / (1.0 + float("inf") if z == float("inf") else float.__pow__(2.0, z))
    else:
        exp_z = float.__pow__(2.0, -z)
        return exp_z / (1.0 + exp_z)


class SimpleLinearModel:
    """A simple linear model that computes p = sigmoid(intercept + sum(weight_i * feature_i)).
    
    The model is loaded from a JSON dict with format:
    {
        "intercept": float,
        "weights": {feature_name: float, ...}
    }
    
    All feature values must be provided during inference. Missing features default to 0.0.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize model from config dict."""
        self.intercept = float(config.get("intercept", 0.0))
        self.weights = config.get("weights", {})
    
    @classmethod
    def load(cls, path: str) -> "SimpleLinearModel":
        """Load model from JSON file."""
        with open(path, "r") as f:
            config = json.load(f)
        return cls(config)
    
    def predict(self, features: Dict[str, float]) -> float:
        """Compute p = sigmoid(intercept + sum(weight_i * feature_i)).
        
        Args:
            features: Dict of feature_name -> value
            
        Returns:
            Probability in [0, 1]
        """
        z = self.intercept
        for feature_name, weight in self.weights.items():
            value = features.get(feature_name, 0.0)
            z += weight * value
        return sigmoid(z)


def infer_p_model(
    features: Dict[str, float],
    *,
    mode: str = "model_off",
    model_path: Optional[str] = None,
) -> Optional[float]:
    """Return model probability/confidence for the trade.
    
    Args:
        features: Dict of feature_name -> value (must match model's expected features)
        mode: Inference mode - "model_off", "heuristic", or "json_weights"
        model_path: Path to model file (required for "json_weights" mode)
    
    Returns:
        Probability in [0, 1] if model is available, None if model is disabled
    """
    if mode == "model_off":
        # Model is disabled - return None for model-off behavior
        return None
    
    if mode == "heuristic":
        # Simple heuristic: high winrate features -> higher probability
        # This is a deterministic fallback when no model is available
        winrate = features.get("f_wallet_winrate_30d", 0.5)
        roi = features.get("f_wallet_roi_30d_pct", 0.0)
        trades = features.get("f_wallet_trades_30d", 10.0)
        
        # Normalize and combine
        winrate_norm = max(0.0, min(1.0, winrate))
        roi_norm = max(0.0, min(1.0, (roi + 50.0) / 100.0))  # Normalize -50..50 to 0..1
        trades_norm = min(1.0, trades / 50.0)  # Cap at 50 trades
        
        # Weighted combination
        p = (0.5 * winrate_norm) + (0.3 * roi_norm) + (0.2 * trades_norm)
        return sigmoid((p - 0.5) * 10.0)  # Sharpen around 0.5
    
    if mode == "json_weights":
        # Load and use JSON linear model
        if model_path is None:
            return None
        
        try:
            model = SimpleLinearModel.load(model_path)
            return model.predict(features)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # Model not found or invalid - fall back to model_off
            return None
    
    # Unknown mode - treat as model_off
    return None
