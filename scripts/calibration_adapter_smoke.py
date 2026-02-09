#!/usr/bin/env python3
"""Smoke test for Calibration Adapter (PR-N.3).

Tests the calibration loader with Platt scaling fixture.

Usage:
    python scripts/calibration_adapter_smoke.py
    bash scripts/calibration_adapter_smoke.sh

Exit codes:
    - 0: All tests passed
    - 1: One or more tests failed
"""

import json
import sys
from pathlib import Path


def run_smoke_tests():
    """Run calibration adapter smoke tests."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    fixture_path = project_root / "integration/fixtures/calibration/platt_fixture.json"
    
    print("[calibration_adapter_smoke] Starting calibration tests...", file=sys.stderr)
    
    try:
        # Add project root to path for imports
        sys.path.insert(0, str(project_root))
        
        # Load fixture
        with open(fixture_path, "r") as f:
            config = json.load(f)
        
        print(f"[calibration_adapter_smoke] Loaded config: {config}", file=sys.stderr)
        
        # Import and create calibrator
        from strategy.calibration_loader import load_calibrator
        
        calibrator = load_calibrator(config)
        
        # Test 1: cal(0.0) == 0.5
        result0 = calibrator(0.0)
        print(f"[calibration_adapter_smoke] cal(0.0) = {result0:.4f}", file=sys.stderr)
        assert abs(result0 - 0.5) < 0.001, f"cal(0.0) should be 0.5, got {result0}"
        
        # Test 2: cal(10.0) -> close to 1.0
        result_positive = calibrator(10.0)
        print(f"[calibration_adapter_smoke] cal(10.0) = {result_positive:.4f}", file=sys.stderr)
        assert result_positive > 0.99, f"cal(10.0) should be > 0.99, got {result_positive}"
        
        # Test 3: cal(-10.0) -> close to 0.0
        result_negative = calibrator(-10.0)
        print(f"[calibration_adapter_smoke] cal(-10.0) = {result_negative:.4f}", file=sys.stderr)
        assert result_negative < 0.01, f"cal(-10.0) should be < 0.01, got {result_negative}"
        
        # Test 4: cal(0.75) for typical raw score
        result_mid = calibrator(0.75)
        print(f"[calibration_adapter_smoke] cal(0.75) = {result_mid:.4f}", file=sys.stderr)
        assert 0.6 < result_mid < 0.9, f"cal(0.75) should be between 0.6 and 0.9, got {result_mid}"
        
        # Test 5: Fail-safe with None config
        print("\n[calibration_adapter_smoke] Testing fail-safe with None config...", file=sys.stderr)
        calibrator_none = load_calibrator(None)
        result_none = calibrator_none(0.5)
        assert result_none == 0.5, f"None config should return identity, got {result_none}"
        print(f"[calibration_adapter_smoke] cal(0.5) with None = {result_none:.4f}", file=sys.stderr)
        
        # Test 6: Fail-safe with empty config
        print("\n[calibration_adapter_smoke] Testing fail-safe with empty config...", file=sys.stderr)
        calibrator_empty = load_calibrator({})
        result_empty = calibrator_empty(0.5)
        assert result_empty == 0.5, f"Empty config should return identity, got {result_empty}"
        print(f"[calibration_adapter_smoke] cal(0.5) with empty = {result_empty:.4f}", file=sys.stderr)
        
        # Test 7: Fail-safe with unknown method
        print("\n[calibration_adapter_smoke] Testing fail-safe with unknown method...", file=sys.stderr)
        calibrator_unknown = load_calibrator({"method": "unknown"})
        result_unknown = calibrator_unknown(0.5)
        assert result_unknown == 0.5, f"Unknown method should return identity, got {result_unknown}"
        print(f"[calibration_adapter_smoke] cal(0.5) with unknown = {result_unknown:.4f}", file=sys.stderr)
        
        print("\n[calibration_adapter_smoke] OK", file=sys.stderr)
        sys.exit(0)
    
    except FileNotFoundError as e:
        print(f"[calibration_adapter_smoke] ERROR: Fixture not found: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[calibration_adapter_smoke] ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except AssertionError as e:
        print(f"[calibration_adapter_smoke] ERROR: Assertion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[calibration_adapter_smoke] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_tests()
