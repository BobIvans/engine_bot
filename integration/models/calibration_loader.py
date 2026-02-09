#!/usr/bin/env python3
"""
integration/models/calibration_loader.py

Calibration Loader for PR-ML.5

Loads and applies model calibration transformations to convert raw
model predictions (p_model_raw) into calibrated probabilities (p_model_calibrated).

Supports:
- Platt scaling: p_calibrated = 1 / (1 + exp(a * p_raw + b))
- Isotonic regression: piecewise-linear monotonic function
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Default calibration storage
_CACHED_CALIBRATORS: Dict[str, "CalibrationLoader"] = {}


class CalibrationLoader:
    """
    Loads and applies calibration transformations.
    
    Supports Platt scaling and Isotonic regression methods.
    Falls back to identity transformation on errors.
    """
    
    def __init__(
        self,
        model_version: Optional[str] = None,
        allow_calibration: bool = True,
        calibration_dir: Optional[str] = None
    ):
        """
        Initialize calibration loader.
        
        Args:
            model_version: Version of calibration to load (e.g., "v1_20250201")
            allow_calibration: Whether to apply calibration (False = identity)
            calibration_dir: Optional custom calibration directory
        """
        self.model_version = model_version
        self.allow_calibration = allow_calibration
        self.calibration_dir = calibration_dir
        self.calibrator: Optional[Callable[[float], float]] = None
        self.calibration_type: Optional[str] = None
        self.metrics: Optional[Dict[str, Any]] = None
        self._is_fallback = False
        
        if allow_calibration and model_version:
            self._load_calibrator()
    
    def _load_calibrator(self) -> None:
        """Load calibration from file."""
        # Determine calibration directory
        if self.calibration_dir is None:
            calibration_dir = Path(__file__).parent.parent / "fixtures" / "ml"
        else:
            calibration_dir = Path(self.calibration_dir)
        
        # Try to load from fixtures first (for testing)
        # Check multiple patterns:
        fixture_patterns = [
            f"calibration_{self.model_version}_sample.json",
            f"calibration_{self.model_version.replace('v', '')}_sample.json",
            f"calibration_{self.model_version.split('_')[0]}_sample.json",
            f"calibration_{self.model_version.split('_')[0].replace('v', 'v')}_sample.json",
        ]
        
        calibration_file = None
        
        # Try all fixture patterns
        for pattern in fixture_patterns:
            fixture_path = calibration_dir / pattern
            if fixture_path.exists():
                calibration_file = fixture_path
                logger.debug(f"[calibration] Found fixture: {fixture_path}")
                break
        
        # Also try data/models directory
        if calibration_file is None:
            data_path = Path("data/models") / f"calibration_{self.model_version}.json"
            if data_path.exists():
                calibration_file = data_path
        
        if calibration_file is None:
            logger.warning(
                f"[calibration] calibration file not found for version {self.model_version}"
            )
            self._set_fallback()
            return
        
        try:
            with open(calibration_file) as f:
                raw = json.load(f)
            
            # Override model_version if loaded from fixture
            if "model_version" in raw:
                self.model_version = raw["model_version"]
            
            self._parse_calibration(raw, calibration_file)
            
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"[calibration] failed to load {calibration_file}: {e}")
            self._set_fallback()
    
    def _parse_calibration(self, raw: Dict, source: Path) -> None:
        """Parse and validate calibration configuration."""
        calibration_type = raw.get("calibration_type")
        
        if calibration_type == "platt":
            self._parse_platt(raw, source)
        elif calibration_type == "isotonic":
            self._parse_isotonic(raw, source)
        else:
            logger.warning(f"[calibration] unknown calibration type: {calibration_type}")
            self._set_fallback()
            return
        
        # Store metrics
        self.metrics = raw.get("metrics", {})
        self.calibration_type = calibration_type
        
        brier = self.metrics.get("brier_score", "N/A")
        ece = self.metrics.get("ece", "N/A")
        logger.info(
            f"[calibration] loaded {calibration_type} calibrator v={self.model_version} "
            f"(Brier={brier}, ECE={ece})"
        )
    
    def _parse_platt(self, raw: Dict, source: Path) -> None:
        """Parse Platt scaling parameters."""
        params = raw.get("params", {})
        a = params.get("a")
        b = params.get("b")
        
        if a is None or b is None:
            logger.warning("[calibration] Platt params missing 'a' or 'b'")
            self._set_fallback()
            return
        
        # Validate monotonicity: a should be negative for proper calibration
        if a >= 0:
            logger.warning(f"[calibration] Platt 'a' should be negative for proper calibration (got {a})")
            # Still allow it but log warning
        
        def platt_scaling(p_raw: float) -> float:
            return 1.0 / (1.0 + math.exp(a * p_raw + b))
        
        self.calibrator = platt_scaling
    
    def _parse_isotonic(self, raw: Dict, source: Path) -> None:
        """Parse Isotonic regression parameters."""
        params = raw.get("params", {})
        x = params.get("x", [])
        y = params.get("y", [])
        
        if len(x) < 2 or len(y) < 2:
            logger.warning("[calibration] Isotonic requires at least 2 points")
            self._set_fallback()
            return
        
        if len(x) != len(y):
            logger.warning("[calibration] Isotonic x and y arrays must have same length")
            self._set_fallback()
            return
        
        # Validate monotonicity: y must be monotonically increasing
        for i in range(len(y) - 1):
            if y[i] > y[i + 1] + 1e-6:
                logger.warning(
                    f"[calibration] Isotonic y-values must be monotonically increasing "
                    f"(got {y[i]} > {y[i+1]})"
                )
                self._set_fallback()
                return
        
        def isotonic_interpolate(p_raw: float) -> float:
            if p_raw <= x[0]:
                return y[0]
            if p_raw >= x[-1]:
                return y[-1]
            
            for i in range(len(x) - 1):
                if x[i] <= p_raw <= x[i + 1]:
                    if x[i + 1] > x[i]:
                        t = (p_raw - x[i]) / (x[i + 1] - x[i])
                    else:
                        t = 0.0
                    return y[i] + t * (y[i + 1] - y[i])
            
            return p_raw  # Fallback
        
        self.calibrator = isotonic_interpolate
    
    def _set_fallback(self) -> None:
        """Set identity fallback calibrator."""
        self.calibrator = lambda p: p
        self._is_fallback = True
        self.calibration_type = "identity"
        logger.info("[calibration] using identity fallback (no calibration)")
    
    def apply(self, p_raw: float) -> float:
        """
        Apply calibration to raw prediction.
        
        Args:
            p_raw: Raw model prediction [0.0, 1.0]
            
        Returns:
            Calibrated probability [0.0, 1.0]
        """
        if not self.allow_calibration or self.calibrator is None:
            return p_raw
        
        p_cal = self.calibrator(p_raw)
        
        # Capping for guaranteed range
        p_cal = max(0.0, min(1.0, p_cal))
        
        return p_cal
    
    def apply_batch(self, p_raw_list: List[float]) -> List[float]:
        """
        Apply calibration to multiple predictions.
        
        Args:
            p_raw_list: List of raw predictions
            
        Returns:
            List of calibrated probabilities
        """
        return [self.apply(p) for p in p_raw_list]
    
    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """Get calibration quality metrics."""
        return self.metrics
    
    def is_identity(self) -> bool:
        """Check if using identity fallback."""
        return self._is_fallback


def get_calibration_loader(
    model_version: Optional[str] = None,
    allow_calibration: bool = True
) -> CalibrationLoader:
    """
    Get or create a cached calibration loader.
    
    Args:
        model_version: Version of calibration to load
        allow_calibration: Whether to apply calibration
        
    Returns:
        CalibrationLoader instance
    """
    cache_key = f"{model_version}:{allow_calibration}"
    
    if cache_key in _CACHED_CALIBRATORS:
        return _CACHED_CALIBRATORS[cache_key]
    
    loader = CalibrationLoader(
        model_version=model_version,
        allow_calibration=allow_calibration
    )
    
    _CACHED_CALIBRATORS[cache_key] = loader
    return loader


def clear_calibration_cache() -> None:
    """Clear cached calibration loaders."""
    _CACHED_CALIBRATORS.clear()
    logger.debug("[calibration] cleared calibration cache")


def save_calibration(
    calibration_type: str,
    params: Dict,
    model_version: str,
    metrics: Dict,
    trained_on: str,
    output_dir: Optional[str] = None
) -> str:
    """
    Save calibration to file.
    
    Args:
        calibration_type: Type of calibration ("platt" or "isotonic")
        params: Calibration parameters
        model_version: Version identifier
        metrics: Quality metrics
        trained_on: Training date
        output_dir: Optional output directory
        
    Returns:
        Path to saved file
    """
    if output_dir is None:
        output_dir = Path("data/models")
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "model_version": model_version,
        "calibration_type": calibration_type,
        "params": params,
        "trained_on": trained_on,
        "metrics": metrics
    }
    
    output_file = output_dir / f"calibration_{model_version}.json"
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"[calibration] saved calibration to {output_file}")
    
    # Clear cache to force reload
    clear_calibration_cache()
    
    return str(output_file)


def main():
    """CLI for calibration loader testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Calibration Loader CLI")
    parser.add_argument("--version", default="v1_20250201", help="Calibration version")
    parser.add_argument("--scores", nargs="+", type=float, default=[0.4, 0.6, 0.8],
                        help="Raw scores to calibrate")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    loader = get_calibration_loader(model_version=args.version)
    
    if args.json:
        results = loader.apply_batch(args.scores)
        print(json.dumps({
            "model_version": args.version,
            "calibration_type": loader.calibration_type,
            "is_fallback": loader.is_identity(),
            "calibrated_scores": results,
            "metrics": loader.get_metrics()
        }, indent=2))
    else:
        print(f"[calibration] Version: {args.version}")
        print(f"[calibration] Type: {loader.calibration_type}")
        print(f"[calibration] Fallback: {loader.is_identity()}")
        print("[calibration] Results:")
        for raw, cal in zip(args.scores, loader.apply_batch(args.scores)):
            print(f"  {raw:.2f} → {cal:.4f}")


if __name__ == "__main__":
    main()
