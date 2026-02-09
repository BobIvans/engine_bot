#!/usr/bin/env python3
"""Smoke test for Latency-Aware Cost Estimator (PR-R.1).

Tests the pure cost calculation function with various network scenarios.

Usage:
    python scripts/latency_smoke.py
    bash scripts/latency_smoke.sh

Exit codes:
    - 0: All test cases passed
    - 1: One or more test cases failed
"""

import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.network_monitor import (
    NetworkStats,
    calculate_latency_cost,
    LatencyParams,
    MAX_LATENCY_COST_BPS,
)


def run_latency_smoke_tests():
    """Run latency cost calculation tests from JSONL fixture."""
    script_dir = Path(__file__).parent
    fixture_path = script_dir / ".." / "integration" / "fixtures" / "latency" / "scenarios.jsonl"
    
    print("[latency_smoke] Starting latency cost tests...", file=sys.stderr)
    
    all_passed = True
    test_count = 0
    passed_count = 0
    
    try:
        with open(fixture_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                test_count += 1
                scenario = json.loads(line)
                description = scenario.get("description", "unknown")
                
                # Create stats from scenario
                stats = NetworkStats(
                    rpc_roundtrip_ms=scenario["rpc_roundtrip_ms"],
                    slot_lag_ms=scenario.get("slot_lag_ms"),
                    measured_at=0,
                    is_estimated=scenario.get("is_estimated", False),
                )
                
                # Create params from scenario
                params = LatencyParams(
                    base_latency_ms=scenario.get("base_latency_ms", 200.0),
                    latency_cost_slope=scenario.get("latency_cost_slope", 0.1),
                    slot_lag_penalty_bps=scenario.get("slot_lag_penalty_bps", 100.0),
                )
                
                # Calculate cost
                cost = calculate_latency_cost(stats, params)
                expected = scenario.get("expected_cost_bps", 0.0)
                
                # Check result
                if abs(cost - expected) < 0.1:
                    passed = True
                    status = "PASS"
                else:
                    passed = False
                    status = f"FAIL (got {cost:.1f}, expected {expected})"
                
                print(f"[latency_smoke] Testing {description}... {status}", file=sys.stderr)
                
                if passed:
                    passed_count += 1
                else:
                    all_passed = False
    
    except FileNotFoundError:
        print(f"[latency_smoke] ERROR: Fixture file not found at {fixture_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[latency_smoke] ERROR: Invalid JSON in fixture: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[latency_smoke] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    
    # Final result
    if all_passed:
        print(f"[latency_smoke] OK ({passed_count}/{test_count} tests passed)", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"[latency_smoke] FAILED ({passed_count}/{test_count} tests passed)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_latency_smoke_tests()
