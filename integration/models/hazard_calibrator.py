#!/usr/bin/env python3
"""
integration/models/hazard_calibrator.py

Hazard Model Calibration Loader.

PR-ML.4

Loads pre-computed calibration curves for transforming raw hazard scores
into calibrated probabilities.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default calibration curve (raw_score -> calibrated_probability)
DEFAULT_CALIBRATION_CURVE: List[Tuple[float, float]] = [
    (0.0, 0.0),
    (0.2, 0.15),
    (0.4, 0.35),
    (0.6, 0.65),
    (0.8, 0.85),
    (1.0, 1.0),
]

# Calibration storage
_CACHED_CURVES: Dict[str, List[Tuple[float, float]]] = {}


def load_hazard_calibration(
    model_version: str = "hazard_v1",
    calibration_dir: Optional[str] = None
) -> List[Tuple[float, float]]:
    """
    Load hazard calibration curve from file.
    
    Args:
        model_version: Version of calibration curve to load
        calibration_dir: Optional custom calibration directory
        
    Returns:
        List of (raw_score, calibrated_score) tuples
        
    Side Effects:
        Logs warning to stderr if calibration file not found
    """
    # Check cache first
    if model_version in _CACHED_CURVES:
        return _CACHED_CURVES[model_version]
    
    # Determine calibration directory
    if calibration_dir is None:
        calibration_dir = Path(__file__).parent.parent / "data" / "models"
    else:
        calibration_dir = Path(calibration_dir)
    
    calibration_file = calibration_dir / f"hazard_calibration_{model_version}.json"
    
    # Try to load from file
    if calibration_file.exists():
        try:
            with open(calibration_file) as f:
                data = json.load(f)
            
            curve = [
                (point["raw"], point["calibrated"])
                for point in data.get("calibration_points", [])
            ]
            
            if curve:
                _CACHED_CURVES[model_version] = curve
                logger.info(f"[hazard_calibrator] Loaded calibration curve {model_version}: {len(curve)} points")
                return curve
                
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"[hazard_calibrator] Failed to load calibration {calibration_file}: {e}")
    
    # Fallback to default
    logger.warning(f"[hazard_calibrator] Using default calibration curve for {model_version}")
    _CACHED_CURVES[model_version] = DEFAULT_CALIBRATION_CURVE
    return DEFAULT_CALIBRATION_CURVE


def save_hazard_calibration(
    calibration_curve: List[Tuple[float, float]],
    model_version: str = "hazard_v1",
    calibration_dir: Optional[str] = None
) -> str:
    """
    Save calibration curve to file.
    
    Args:
        calibration_curve: List of (raw_score, calibrated_score) tuples
        model_version: Version identifier
        calibration_dir: Optional custom directory
        
    Returns:
        Path to saved file
    """
    if calibration_dir is None:
        calibration_dir = Path(__file__).parent.parent / "data" / "models"
    else:
        calibration_dir = Path(calibration_dir)
    
    # Ensure directory exists
    calibration_dir.mkdir(parents=True, exist_ok=True)
    
    calibration_file = calibration_dir / f"hazard_calibration_{model_version}.json"
    
    data = {
        "model_version": model_version,
        "calibration_points": [
            {"raw": raw, "calibrated": calibrated}
            for raw, calibrated in calibration_curve
        ],
        "created_ts": int(time.time()),
    }
    
    with open(calibration_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"[hazard_calibrator] Saved calibration curve to {calibration_file}")
    
    # Update cache
    _CACHED_CURVES[model_version] = calibration_curve
    
    return str(calibration_file)


def clear_calibration_cache() -> None:
    """Clear cached calibration curves."""
    _CACHED_CURVES.clear()
    logger.debug("[hazard_calibrator] Cleared calibration cache")


def get_default_calibration() -> List[Tuple[float, float]]:
    """Get the default calibration curve."""
    return DEFAULT_CALIBRATION_CURVE.copy()


def main():
    """CLI for calibration management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Hazard calibration management")
    parser.add_argument("--load", action="store_true", help="Load calibration curve")
    parser.add_argument("--model-version", default="hazard_v1", help="Model version")
    parser.add_argument("--save", action="store_true", help="Save default calibration")
    parser.add_argument("--list", action="store_true", help="List cached curves")
    
    args = parser.parse_args()
    
    if args.load:
        curve = load_hazard_calibration(args.model_version)
        print(f"[hazard_calibrator] Loaded {len(curve)} calibration points:")
        for raw, calibrated in curve:
            print(f"  raw={raw:.2f} -> calibrated={calibrated:.2f}")
    
    if args.save:
        curve = get_default_calibration()
        save_hazard_calibration(curve, args.model_version)
        print(f"[hazard_calibrator] Saved default calibration for {args.model_version}")
    
    if args.list:
        print(f"[hazard_calibrator] Cached curves: {list(_CACHED_CURVES.keys())}")


if __name__ == "__main__":
    main()
