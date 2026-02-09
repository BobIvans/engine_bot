#!/usr/bin/env python3
"""strategy/calibration.py

PR-N.1 Probability Calibration Module

Pure functions for calibrating raw model scores to calibrated probabilities.
Used by risk engine (Kelly) to ensure confidence values match empirical success rates.

Supported methods:
- "none": Identity (return raw score)
- "platt": Platt scaling with logit transformation
- "clipping": Clip values to min/max bounds

All functions are pure (deterministic, no I/O).
"""

from __future__ import annotations

import math
from typing import Any, Dict


# Small epsilon for numerical stability
_EPS = 1e-15


def _safe_sigmoid(x: float) -> float:
    """Numerically stable sigmoid function.
    
    Args:
        x: Input value (can be any real number)
    
    Returns:
        Value in (0, 1) range
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)


def _safe_logit(p: float) -> float:
    """Numerically stable logit (inverse sigmoid) function.
    
    Args:
        p: Probability in (0, 1) range
    
    Returns:
        Log-odds (can be any real number)
    
    Raises:
        ValueError: If p is outside (0, 1) range
    """
    if p <= 0 or p >= 1:
        raise ValueError(f"logit requires p in (0, 1), got {p}")
    
    # Clamp to avoid numerical issues at boundaries
    p = max(_EPS, min(1.0 - _EPS, p))
    return math.log(p / (1.0 - p))


def _platt_scale(logit_score: float, a: float, b: float) -> float:
    """Apply Platt scaling parameters to log-odds.
    
    Args:
        logit_score: Input in log-odds space
        a: Scale parameter (Platt A)
        b: Bias parameter (Platt B)
    
    Returns:
        Calibrated probability
    """
    return _safe_sigmoid(a * logit_score + b)


def calibrate_probability(raw_score: float, cfg: Dict[str, Any]) -> float:
    """Calibrate raw model score to probability.
    
    Pure function: output depends only on inputs.
    
    Args:
        raw_score: Raw model output (expected in [0, 1] range)
        cfg: Configuration dict with calibration parameters
            Expected structure:
            {
                "model": {
                    "calibration": {
                        "method": "none" | "platt" | "clipping",
                        # For Platt:
                        "platt_a": float,  # scale parameter
                        "platt_b": float,  # bias parameter
                        # For clipping:
                        "min_prob": float,  # default 0.001
                        "max_prob": float,  # default 0.999
                    }
                }
            }
    
    Returns:
        Calibrated probability in [0, 1] range
    
    Examples:
        >>> # Identity calibration
        >>> cfg = {"model": {"calibration": {"method": "none"}}}
        >>> calibrate_probability(0.7, cfg)
        0.7
        
        >>> # Platt scaling (score in [0,1])
        >>> cfg = {"model": {"calibration": {
        ...     "method": "platt",
        ...     "platt_a": -1.5,
        ...     "platt_b": 0.2
        ... }}}
        >>> calibrate_probability(0.5, cfg)  # doctest: +ELLIPSIS
        0....
        
        >>> # Clipping
        >>> cfg = {"model": {"calibration": {
        ...     "method": "clipping",
        ...     "min_prob": 0.01,
        ...     "max_prob": 0.99
        ... }}}
        >>> calibrate_probability(0.005, cfg)
        0.01
    """
    # Extract calibration config with defaults
    model_cfg = cfg.get("model", {})
    cal_cfg = model_cfg.get("calibration", {})
    
    method = cal_cfg.get("method", "none").lower()
    
    # Validate input range
    if not (0 <= raw_score <= 1):
        raise ValueError(f"raw_score must be in [0, 1], got {raw_score}")
    
    if method == "none":
        # Identity: return as-is
        return raw_score
    
    elif method == "platt":
        # Platt scaling: convert to logit, apply affine transform, convert back
        a = cal_cfg.get("platt_a", 1.0)
        b = cal_cfg.get("platt_b", 0.0)
        
        # Handle edge cases for scores at boundaries
        if raw_score <= _EPS:
            return _safe_sigmoid(a * _safe_logit(_EPS) + b)
        elif raw_score >= 1.0 - _EPS:
            return _safe_sigmoid(a * _safe_logit(1.0 - _EPS) + b)
        
        # Convert to log-odds, apply Platt parameters
        logit_score = _safe_logit(raw_score)
        calibrated = _platt_scale(logit_score, a, b)
        
        # Ensure output is in valid range
        return max(0.0, min(1.0, calibrated))
    
    elif method == "clipping":
        # Simple min/max clipping
        min_prob = cal_cfg.get("min_prob", 0.001)
        max_prob = cal_cfg.get("max_prob", 0.999)
        
        return max(min_prob, min(max_prob, raw_score))
    
    else:
        raise ValueError(f"Unknown calibration method: {method}")


def calibrate_batch(
    raw_scores: list[float], 
    cfg: Dict[str, Any]
) -> list[float]:
    """Calibrate multiple scores efficiently.
    
    Args:
        raw_scores: List of raw model scores
        cfg: Configuration dict (passed to calibrate_probability)
    
    Returns:
        List of calibrated probabilities
    
    Examples:
        >>> cfg = {"model": {"calibration": {"method": "none"}}}
        >>> calibrate_batch([0.3, 0.5, 0.7], cfg)
        [0.3, 0.5, 0.7]
    """
    return [calibrate_probability(score, cfg) for score in raw_scores]


# Alias for common usage
calibrate = calibrate_probability


if __name__ == "__main__":
    # Simple CLI demo
    import json
    
    # Default identity config
    identity_cfg = {"model": {"calibration": {"method": "none"}}}
    
    print("Calibration Module Demo")
    print("=" * 40)
    
    # Test identity
    print("\n1. Identity (method='none'):")
    for score in [0.0, 0.3, 0.5, 0.7, 1.0]:
        calibrated = calibrate_probability(score, identity_cfg)
        print(f"   {score:.2f} -> {calibrated:.4f}")
    
    # Test Platt scaling
    platt_cfg = {
        "model": {
            "calibration": {
                "method": "platt",
                "platt_a": -1.5,
                "platt_b": 0.2
            }
        }
    }
    
    print("\n2. Platt Scaling (a=-1.5, b=0.2):")
    for score in [0.1, 0.3, 0.5, 0.7, 0.9]:
        calibrated = calibrate_probability(score, platt_cfg)
        print(f"   {score:.2f} -> {calibrated:.4f}")
    
    # Test clipping
    clip_cfg = {
        "model": {
            "calibration": {
                "method": "clipping",
                "min_prob": 0.01,
                "max_prob": 0.99
            }
        }
    }
    
    print("\n3. Clipping (min=0.01, max=0.99):")
    for score in [0.0, 0.005, 0.5, 0.995, 1.0]:
        calibrated = calibrate_probability(score, clip_cfg)
        print(f"   {score:.3f} -> {calibrated:.4f}")
