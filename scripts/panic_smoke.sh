#!/usr/bin/env python3
"""scripts/panic_smoke.sh

Smoke test for ops/panic.py module.
Tests the kill-switch mechanism by creating/removing the sentinel file.
"""
import os
import sys

# Ensure we can import from the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ops.panic import check_panic, create_panic, clear_panic, STOP_STRATEGY

def main() -> int:
    errors = []
    
    # Ensure clean state
    if os.path.exists(STOP_STRATEGY):
        os.remove(STOP_STRATEGY)
    
    # Test 1: No panic file -> False
    result = check_panic()
    if result:
        errors.append(f"Test 1 FAILED: Expected False, got {result}")
        print("[panic_smoke] Test 1 FAILED: Expected False without panic file", file=sys.stderr)
    else:
        print("[panic_smoke] Test 1 PASSED: check_panic() == False", file=sys.stderr)
    
    # Test 2: Create panic file -> True
    create_panic()
    result = check_panic()
    if not result:
        errors.append(f"Test 2 FAILED: Expected True, got {result}")
        print("[panic_smoke] Test 2 FAILED: Expected True with panic file", file=sys.stderr)
    else:
        print("[panic_smoke] Test 2 PASSED: check_panic() == True", file=sys.stderr)
    
    # Test 3: Remove panic file -> False
    clear_panic()
    result = check_panic()
    if result:
        errors.append(f"Test 3 FAILED: Expected False, got {result}")
        print("[panic_smoke] Test 3 FAILED: Expected False after clearing panic", file=sys.stderr)
    else:
        print("[panic_smoke] Test 3 PASSED: check_panic() == False", file=sys.stderr)
    
    # Test 4: Check file path constant
    if STOP_STRATEGY != "STOP_STRATEGY":
        errors.append(f"Test 4 FAILED: STOP_STRATEGY != 'STOP_STRATEGY', got '{STOP_STRATEGY}'")
        print(f"[panic_smoke] Test 4 FAILED: STOP_STRATEGY = '{STOP_STRATEGY}'", file=sys.stderr)
    else:
        print("[panic_smoke] Test 4 PASSED: STOP_STRATEGY constant correct", file=sys.stderr)
    
    # Clean up
    if os.path.exists(STOP_STRATEGY):
        os.remove(STOP_STRATEGY)
    
    if errors:
        print("\n[panic_smoke] ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("\n[panic_smoke] FAILED", file=sys.stderr)
        return 1
    
    print("[panic_smoke] OK", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
