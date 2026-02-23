"""strategy/calibration_adapter.py

PR-N.3 Calibrated Inference Adapter

Wraps base model with calibration layer to convert raw scores to calibrated
probabilities p_model for correct EV calculation.

Usage:
    calibrator = load_calibrator_from_file("calibration.json")
    calibrated_predictor = CalibratedPredictor(base_model, calibrator)
    p_calibrated = calibrated_predictor.predict_proba(features_dict)
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Dict, Optional

# Try to import from strategy package, fall back for standalone use
try:
    from strategy.calibration_loader import load_calibrator
except ModuleNotFoundError:
    from calibration_loader import load_calibrator


class CalibratedPredictor:
    """Wrapper that applies calibration to model predictions.

    Attributes:
        base_model: Object with predict_proba(x: Dict) -> float method.
                    Must accept Dict input and return raw score in [0, 1].
        calibrator: Callable[[float], float] or None.
                    Takes raw score, returns calibrated probability.
                    If None, returns raw score with warning.
    """

    def __init__(
        self,
        base_model: Any,
        calibrator: Optional[Callable[[float], float]] = None,
    ) -> None:
        """Initialize calibrated predictor.

        Args:
            base_model: Model with predict_proba(features_dict) -> float.
            calibrator: Optional calibrator function. If None, identity is used.
        """
        self.base_model = base_model
        self.calibrator = calibrator

        # Setup logging
        self._logger = logging.getLogger(__name__)
        self._logger.addHandler(logging.StreamHandler(sys.stderr))
        self._logger.setLevel(logging.WARNING)

    def predict_proba(self, x: Dict[str, Any]) -> float:
        """Get calibrated probability from model.

        Args:
            x: Feature dictionary for model inference.

        Returns:
            Probability in [0, 1] range (calibrated if calibrator available).

        Raises:
            ValueError: If model returns score outside [0, 1].
        """
        # Get raw score from base model
        raw = self.base_model.predict_proba(x)

        # Validate raw score range
        if not (0.0 <= raw <= 1.0):
            raise ValueError(
                f"Model returned invalid raw score: {raw}. Expected [0, 1]."
            )

        # Apply calibration if available
        if self.calibrator is not None:
            calibrated = self.calibrator(raw)
            # Ensure result is in valid range
            return max(0.0, min(1.0, calibrated))
        else:
            self._logger.warning(
                "calibration_adapter: No calibrator configured, returning raw score"
            )
            return raw

    def predict_proba_batch(
        self, batch: list[Dict[str, Any]]
    ) -> list[float]:
        """Get calibrated probabilities for a batch of inputs.

        Args:
            batch: List of feature dictionaries.

        Returns:
            List of calibrated probabilities.
        """
        return [self.predict_proba(x) for x in batch]


def create_calibrated_predictor(
    base_model: Any,
    calibration_path: Optional[str] = None,
) -> CalibratedPredictor:
    """Factory function to create calibrated predictor.

    Args:
        base_model: Model with predict_proba(features_dict) -> float.
        calibration_path: Optional path to calibration config JSON file.
                         If None, uses identity (no calibration).

    Returns:
        CalibratedPredictor instance.
    """
    calibrator = None
    if calibration_path:
        try:
            calibrator = load_calibrator_from_file(calibration_path)
        except (FileNotFoundError, ValueError) as e:
            logging.warning(
                f"calibration_adapter: Failed to load calibrator from "
                f"{calibration_path}: {e}. Using identity."
            )
            calibrator = None

    return CalibratedPredictor(base_model, calibrator)


def load_calibrator_from_file(path: str) -> Callable[[float], float]:
    """Load calibrator from JSON file.

    Args:
        path: Path to calibration config JSON file.

    Returns:
        Calibrator function: float -> float.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If file contains invalid JSON or missing required fields.
    """
    import json

    with open(path, "r") as f:
        config = json.load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid calibration config: expected dict, got {type(config)}")

    return load_calibrator(config)


# Self-test
if __name__ == "__main__":
    import json

    print("=== CalibratedPredictor Self-Test ===", file=sys.stderr)

    # Mock base model for testing
    class MockModel:
        def predict_proba(self, x: Dict) -> float:
            return x.get("raw_score", 0.5)

    # Test 1: With Platt calibrator (a=1, b=0, standard sigmoid)
    print("\nTest 1: Platt calibrator (a=1, b=0)", file=sys.stderr)
    platt_config = {"method": "platt", "params": {"a": 1.0, "b": 0.0}}
    calibrator = load_calibrator(platt_config)
    predictor = CalibratedPredictor(MockModel(), calibrator)

    # Test with valid [0,1] scores (MockModel returns raw_score directly)
    # Platt(a=1, b=0) on 0.0: 1/(1+exp(0)) = 0.5
    result = predictor.predict_proba({"raw_score": 0.0})
    print(f"  cal(0.0) = {result:.4f} (expected ~0.5)", file=sys.stderr)
    assert abs(result - 0.5) < 0.001, f"Expected 0.5, got {result}"

    # Platt on 1.0: 1/(1+exp(-1)) = ~0.731
    result = predictor.predict_proba({"raw_score": 1.0})
    print(f"  cal(1.0) = {result:.4f} (expected ~0.731)", file=sys.stderr)
    assert abs(result - 0.731) < 0.01, f"Expected ~0.731, got {result}"

    # Platt on 0.5: 1/(1+exp(-0.5)) = ~0.622
    result = predictor.predict_proba({"raw_score": 0.5})
    print(f"  cal(0.5) = {result:.4f} (expected ~0.622)", file=sys.stderr)
    assert abs(result - 0.622) < 0.01, f"Expected ~0.622, got {result}"

    # Test 2: No calibrator (identity)
    print("\nTest 2: No calibrator (identity)", file=sys.stderr)
    predictor_no_cal = CalibratedPredictor(MockModel(), None)
    result = predictor_no_cal.predict_proba({"raw_score": 0.75})
    print(f"  raw(0.75) = {result:.4f} (expected 0.7500)", file=sys.stderr)
    assert result == 0.75, f"Expected 0.75, got {result}"

    # Test 3: Monotonicity check
    print("\nTest 3: Monotonicity preservation", file=sys.stderr)
    scores = [0.0, 0.25, 0.5, 0.75, 1.0]
    calibrated = [predictor.predict_proba({"raw_score": s}) for s in scores]
    print(f"  scores: {[f'{s:.2f}' for s in scores]}", file=sys.stderr)
    print(f"  calibrated: {[f'{c:.4f}' for c in calibrated]}", file=sys.stderr)

    # Verify monotonicity
    for i in range(len(calibrated) - 1):
        assert calibrated[i] <= calibrated[i + 1], (
            f"Monotonicity violated: {calibrated[i]} > {calibrated[i + 1]}"
        )
    print("  Monotonicity: OK", file=sys.stderr)

    # Test 4: Range check
    print("\nTest 4: Output range [0, 1]", file=sys.stderr)
    for s in [-100.0, -10.0, 0.0, 0.5, 10.0, 100.0]:
        c = predictor.predict_proba({"raw_score": s})
        assert 0.0 <= c <= 1.0, f"Output {c} out of range for input {s}"
    print("  Range check: OK", file=sys.stderr)

    print("\n=== All tests passed! ===", file=sys.stderr)
