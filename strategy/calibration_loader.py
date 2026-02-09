"""strategy/calibration_loader.py - Calibration Adapter for Model Scores

Pure logic for converting raw model scores to calibrated probabilities.
Supports Platt Scaling (sigmoid) for probability calibration.

This module is pure: it takes a Dict (loaded from JSON) and returns
a Callable[[float], float]. No file I/O, no side effects.

Usage:
    calibrator = load_calibrator({"method": "platt", "params": {"a": 1.0, "b": 0.0}})
    calibrated_prob = calibrator(raw_score)  # 0.0 - 1.0
"""

from __future__ import annotations

import logging
import math
import sys
from typing import Any, Callable, Dict, Optional

# Configure logging to stderr only (no print() in strategy/)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.WARNING)


# Default Platt parameters (identity-like transformation)
DEFAULT_PLATT_A = 1.0
DEFAULT_PLATT_B = 0.0


def load_calibrator(config: Optional[Dict[str, Any]]) -> Callable[[float], float]:
    """Load calibration function from configuration dict.
    
    Pure function: takes config Dict, returns calibrator Callable.
    
    Args:
        config: Calibration config with structure:
            {
                "method": "platt" | "identity",
                "params": {"a": float, "b": float}  # for platt
            }
            If None or empty, returns identity function.
    
    Returns:
        Calibrator function: float -> float (in range [0, 1])
    
    Fail-Safe:
        - Missing/invalid config -> identity function
        - Logs WARNING to stderr for debugging
    """
    # Handle None or empty config
    if not config:
        logger.warning("calibration_loader: No config provided, using identity")
        return _identity
    
    # Check for method
    method = config.get("method", "identity")
    
    if method == "platt":
        return _create_platt_calibrator(config.get("params"))
    elif method == "identity":
        return _identity
    else:
        logger.warning(f"calibration_loader: Unknown method '{method}', using identity")
        return _identity


def _create_platt_calibrator(params: Optional[Dict[str, Any]]) -> Callable[[float], float]:
    """Create Platt scaling calibrator.
    
    Platt Scaling formula:
        P(y=1|x) = 1 / (1 + exp(-(a * x + b)))
    
    Args:
        params: Dict with "a" and "b" coefficients.
    
    Returns:
        Platt calibrator function.
    """
    if not params:
        logger.warning("calibration_loader: No params for platt, using defaults")
        a = DEFAULT_PLATT_A
        b = DEFAULT_PLATT_B
    else:
        a = params.get("a", DEFAULT_PLATT_A)
        b = params.get("b", DEFAULT_PLATT_B)
    
    # Validate types
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        logger.warning(f"calibration_loader: Invalid platt params a={a}, b={b}, using defaults")
        a = DEFAULT_PLATT_A
        b = DEFAULT_PLATT_B
    
    def calibrator(x: float) -> float:
        """Apply Platt scaling to raw score."""
        # Clamp input to prevent overflow
        clamped_x = max(-500.0, min(500.0, x))
        return 1.0 / (1.0 + math.exp(-(a * clamped_x + b)))
    
    return calibrator


def _identity(x: float) -> float:
    """Identity function (no calibration)."""
    return x


# Convenience function for direct use
def create_identity() -> Callable[[float], float]:
    """Create identity calibrator."""
    return _identity


def create_platt(a: float = DEFAULT_PLATT_A, b: float = DEFAULT_PLATT_B) -> Callable[[float], float]:
    """Create Platt calibrator with given parameters."""
    def calibrator(x: float) -> float:
        clamped_x = max(-500.0, min(500.0, x))
        return 1.0 / (1.0 + math.exp(-(a * clamped_x + b)))
    return calibrator


# Self-test when run directly
if __name__ == "__main__":
    import json
    
    print("=== Calibration Loader Self-Test ===", file=sys.stderr)
    
    # Test 1: Standard Platt (a=1, b=0)
    print("\nTest 1: Standard Platt (a=1, b=0)", file=sys.stderr)
    config1 = {"method": "platt", "params": {"a": 1.0, "b": 0.0}}
    cal1 = load_calibrator(config1)
    
    assert abs(cal1(0.0) - 0.5) < 0.001, "cal(0) should be 0.5"
    print(f"  cal(0.0) = {cal1(0.0):.4f} (expected 0.5)", file=sys.stderr)
    
    result_positive = cal1(10.0)
    assert result_positive > 0.99, "cal(10) should be close to 1.0"
    print(f"  cal(10.0) = {result_positive:.4f} (expected ~1.0)", file=sys.stderr)
    
    result_negative = cal1(-10.0)
    assert result_negative < 0.01, "cal(-10) should be close to 0.0"
    print(f"  cal(-10.0) = {result_negative:.4f} (expected ~0.0)", file=sys.stderr)
    
    # Test 2: Identity
    print("\nTest 2: Identity", file=sys.stderr)
    config2 = {"method": "identity"}
    cal2 = load_calibrator(config2)
    
    assert cal2(0.75) == 0.75, "identity should return same value"
    print(f"  cal(0.75) = {cal2(0.75):.4f} (expected 0.75)", file=sys.stderr)
    
    # Test 3: None config (fail-safe)
    print("\nTest 3: None config (fail-safe)", file=sys.stderr)
    cal3 = load_calibrator(None)
    
    assert cal3(0.5) == 0.5, "None config should return identity"
    print(f"  cal(0.5) = {cal3(0.5):.4f} (expected 0.5)", file=sys.stderr)
    
    # Test 4: Unknown method (fail-safe)
    print("\nTest 4: Unknown method (fail-safe)", file=sys.stderr)
    config4 = {"method": "unknown_method"}
    cal4 = load_calibrator(config4)
    
    assert cal4(0.5) == 0.5, "Unknown method should return identity"
    print(f"  cal(0.5) = {cal4(0.5):.4f} (expected 0.5)", file=sys.stderr)
    
    # Test 5: Empty params (fail-safe with defaults)
    print("\nTest 5: Empty params (fail-safe with defaults)", file=sys.stderr)
    config5 = {"method": "platt", "params": {}}
    cal5 = load_calibrator(config5)
    
    assert abs(cal5(0.0) - 0.5) < 0.001, "Empty params should use defaults"
    print(f"  cal(0.0) = {cal5(0.0):.4f} (expected 0.5)", file=sys.stderr)
    
    print("\n=== All tests passed! ===", file=sys.stderr)
