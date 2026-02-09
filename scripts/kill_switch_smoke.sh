#!/bin/bash
# scripts/kill_switch_smoke.sh
# Smoke test for PR-Z.1 Master Kill-Switch (Panic Button)
# Fully offline, deterministic, no network calls

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="${ROOT_DIR}/integration/fixtures/panic"

# Set PYTHONPATH for imports
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"

fail() {
    echo -e "${RED}[kill_switch_smoke] FAIL: $*${NC}" >&2
    exit 1
}

pass() {
    echo -e "${GREEN}[kill_switch_smoke] $*${NC}" >&2
}

log() {
    echo -e "[kill_switch_smoke] $*" >&2
}

# === Smoke Test ===
log "Starting kill switch smoke test..."

# Test 1: Import panic module
log "Test 1: Importing panic module..."
python3 -c "from ops.panic import is_panic_active, get_panic_reason, create_panic_flag, clear_panic_flag, PanicShutdown, require_no_panic; print('Import OK')" || fail "Failed to import panic module"
pass "Test 1 passed: Module import"

# Test 2: Run panic.py self-test
log "Test 2: Running panic.py self-test..."
python3 "${ROOT_DIR}/ops/panic.py" 2>&1 | tail -10 || fail "panic.py self-test failed"
pass "Test 2 passed: panic.py self-test"

# Test 3: Import kill_switch module
log "Test 3: Importing kill_switch module..."
python3 -c "from ops.kill_switch import KillSwitch, KillSwitchConfig, check_panic, force_close_all_positions, load_kill_switch_config; print('Import OK')" || fail "Failed to import kill_switch module"
pass "Test 3 passed: kill_switch module import"

# Test 4: Run kill_switch.py self-test
log "Test 4: Running kill_switch.py self-test..."
python3 "${ROOT_DIR}/ops/kill_switch.py" 2>&1 | tail -10 || fail "kill_switch.py self-test failed"
pass "Test 4 passed: kill_switch.py self-test"

# Test 5: Verify fixtures exist
log "Test 5: Checking fixtures..."
[[ -f "${FIXTURE_DIR}/panic_flag_content.txt" ]] || fail "Missing fixture: panic_flag_content.txt"
[[ -f "${FIXTURE_DIR}/expected_stop_log.txt" ]] || fail "Missing fixture: expected_stop_log.txt"
pass "Test 5 passed: Fixtures exist"

# Test 6: Test panic activation without real harm
log "Test 6: Testing panic activation (simulation)..."

python3 << 'PYEOF'
import sys
import tempfile
import os

sys.path.insert(0, '.')

from ops.panic import (
    is_panic_active,
    get_panic_reason,
    create_panic_flag,
    clear_panic_flag,
    require_no_panic,
    PanicShutdown,
    clear_panic_cache,
)

# Use temp file for testing
test_flag = tempfile.mktemp(suffix="_panic_test.flag")

# Ensure clean state
if os.path.exists(test_flag):
    os.remove(test_flag)

# Verify inactive
assert not is_panic_active(test_flag), "Should be inactive"
print(f"  Initial state: is_panic_active = False", file=sys.stderr)

# Create panic flag
create_panic_flag(test_flag, "SMOKE_TEST_PANIC")
assert is_panic_active(test_flag), "Should be active after creation"
print(f"  After creation: is_panic_active = True", file=sys.stderr)

# Verify reason
reason = get_panic_reason(test_flag)
assert reason == "SMOKE_TEST_PANIC", f"Expected 'SMOKE_TEST_PANIC', got '{reason}'"
print(f"  Reason: '{reason}'", file=sys.stderr)

# Verify require_no_panic raises
try:
    require_no_panic(test_flag)
    print("  FAIL: Should have raised PanicShutdown", file=sys.stderr)
    sys.exit(1)
except PanicShutdown as e:
    print(f"  PanicShutdown raised correctly: '{e.reason}'", file=sys.stderr)

# Clear flag
assert clear_panic_flag(test_flag), "Should return True"
assert not is_panic_active(test_flag), "Should be inactive after clear"
print(f"  After clear: is_panic_active = False", file=sys.stderr)

# Clear cache
clear_panic_cache()

print("  Panic activation test passed", file=sys.stderr)
PYEOF

pass "Test 6 passed: Panic activation simulation"

# Test 7: Test KillSwitch class
log "Test 7: Testing KillSwitch class..."

python3 << 'PYEOF'
import sys
import tempfile
import os

sys.path.insert(0, '.')

from ops.kill_switch import KillSwitch, KillSwitchConfig

# Use temp file
test_flag = tempfile.mktemp(suffix="_kill_test.flag")

# Test default config
config = KillSwitchConfig(
    flag_path=test_flag,
    enabled=True,
    on_panic="close_all_market",
)

ks = KillSwitch(config=config)

# Check initial status
status = ks.get_status()
assert status["enabled"] == True
assert status["active"] == False
assert status["flag_path"] == test_flag
print(f"  Initial status: {status}", file=sys.stderr)

# Create panic flag
with open(test_flag, "w") as f:
    f.write("SMOKE_TEST_KILL_SWITCH")

status = ks.get_status()
assert status["active"] == True
assert status["reason"] == "SMOKE_TEST_KILL_SWITCH"
print(f"  Active status: {status}", file=sys.stderr)

# Cleanup
os.remove(test_flag)

print("  KillSwitch class test passed", file=sys.stderr)
PYEOF

pass "Test 7 passed: KillSwitch class"

# Test 8: Test load_kill_switch_config
log "Test 8: Testing config loading from dict..."

python3 << 'PYEOF'
import sys

sys.path.insert(0, '.')

from ops.kill_switch import load_kill_switch_config, DEFAULT_PANIC_FLAG_PATH

# Test with minimal config
config_dict_minimal = {"panic": {}}
config = load_kill_switch_config(config_dict_minimal)
assert config.enabled == True
assert config.flag_path == DEFAULT_PANIC_FLAG_PATH
print(f"  Minimal config: enabled={config.enabled}, flag={config.flag_path}", file=sys.stderr)

# Test with full config
config_dict_full = {
    "panic": {
        "enabled": False,
        "flag_path": "/custom/path/panic.flag",
        "on_panic": "hard_stop",
        "cache_ttl_seconds": 5.0,
    }
}
config = load_kill_switch_config(config_dict_full)
assert config.enabled == False
assert config.flag_path == "/custom/path/panic.flag"
assert config.on_panic == "hard_stop"
assert config.cache_ttl_seconds == 5.0
print(f"  Full config: enabled={config.enabled}, flag={config.flag_path}", file=sys.stderr)

print("  Config loading test passed", file=sys.stderr)
PYEOF

pass "Test 8 passed: Config loading"

# === All Tests Passed ===
echo ""
echo -e "${GREEN}[kill_switch_smoke] OK${NC}" >&2
exit 0
