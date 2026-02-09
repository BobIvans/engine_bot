#!/bin/bash
# scripts/key_gate_smoke.sh
# PR-G.3 Live Config Gate & Key Management - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"

echo "[key_gate_smoke] Starting key gate smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import os
import tempfile
import json

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [key_gate] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [key_gate] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[key_gate_smoke] Testing key_manager...", file=sys.stderr)

from integration.key_manager import (
    load_solana_private_key,
    load_signing_key,
    validate_key_exists,
    KeyLoadError,
)

# Test 1: validate_key_exists returns False when key not set
os.environ.pop("SOLANA_PRIVATE_KEY", None)
test_case("no_key_when_not_set", validate_key_exists() == False)

# Test 2: load_solana_private_key raises error when key not set
try:
    load_solana_private_key()
    test_case("error_when_key_missing", False, "Should have raised KeyLoadError")
except KeyLoadError as e:
    test_case("error_when_key_missing", "not set" in str(e))

# Test 3: Load JSON array format (mock valid format)
fake_json_key = "[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64]"
os.environ["SOLANA_PRIVATE_KEY"] = fake_json_key
test_case("json_array_format_accepted", validate_key_exists() == True)

# Test 4: Load empty string raises error
os.environ["SOLANA_PRIVATE_KEY"] = ""
try:
    load_solana_private_key()
    test_case("empty_string_rejected", False, "Should have raised KeyLoadError")
except KeyLoadError as e:
    test_case("empty_string_rejected", True)

print("[key_gate_smoke] Testing config gate...", file=sys.stderr)

# Read the actual config file and check for safety section
from integration.config_loader import load_params_base

loaded = load_params_base("$ROOT_DIR/strategy/config/params_base.yaml")
cfg = loaded.config

# Test 5: Verify safety section exists in real config
safety_cfg = cfg.get("run", {}).get("safety", {})
test_case("safety_section_exists", "live_trading_enabled" in safety_cfg)

# Test 6: Verify default is false
test_case("live_disabled_by_default", safety_cfg.get("live_trading_enabled") == False)

# Test 7: Verify reject constants exist
from integration.reject_reasons import DUPLICATE_EXECUTION, TX_DROPPED, TX_REORGED
test_case("reject_duplicate_exists", DUPLICATE_EXECUTION == "duplicate_execution")
test_case("reject_dropped_exists", TX_DROPPED == "tx_dropped")
test_case("reject_reorged_exists", TX_REORGED == "tx_reorged")

# Summary
print(f"\n[key_gate_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[key_gate_smoke] OK", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[key_gate_smoke] Smoke test completed." >&2
