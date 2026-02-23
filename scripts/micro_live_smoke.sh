#!/bin/bash
# scripts/micro_live_smoke.sh
# Smoke test for Micro-Live Execution Mode Safety Guard
# PR-U.5

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[micro_live_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[micro_live_smoke] ERROR:${NC} $1" >&2
    exit 1
}

log_reject() {
    echo -e "${YELLOW}[micro_live_smoke]${NC} $1"
}

# Add project root to PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

echo ""
log_info "Starting Micro-Live Safety Guard smoke tests..."
echo ""

python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

from execution.safety.micro_guard import (
    MicroSafetyGuard,
    SafetyConfig,
    SafetyViolationError,
    MAX_MICRO_TRADE_SOL,
    MAX_MICRO_DAILY_LOSS_SOL,
    MAX_MICRO_EXPOSURE_SOL,
)

print("[micro_live_smoke] Testing hard-coded constants...")
print(f"  MAX_MICRO_TRADE_SOL = {MAX_MICRO_TRADE_SOL} (OK)")
print(f"  MAX_MICRO_DAILY_LOSS_SOL = {MAX_MICRO_DAILY_LOSS_SOL} (OK)")
print(f"  MAX_MICRO_EXPOSURE_SOL = {MAX_MICRO_EXPOSURE_SOL} (OK)")
print("")

# Verify hard-coded values
assert MAX_MICRO_TRADE_SOL == 0.1, "MAX_MICRO_TRADE_SOL must be 0.1"
assert MAX_MICRO_DAILY_LOSS_SOL == 0.5, "MAX_MICRO_DAILY_LOSS_SOL must be 0.5"
assert MAX_MICRO_EXPOSURE_SOL == 1.0, "MAX_MICRO_EXPOSURE_SOL must be 1.0"

# Test configuration
print("[micro_live_smoke] Testing SafetyConfig...")
config = SafetyConfig(
    max_trade_sol=0.05,
    max_daily_loss_sol=0.2,
    allowed_wallets=[
        "7nYhPEv7z5VnKMj4m6kV4qZz5v8p7Gw8q5dRt5k2w3xF",
        "9mZRQ8dD4mVZ1j4f5mZ8v2a9b6c1e0f3g4h5i6j7k8l9m",
    ]
)
assert config.max_trade_sol == 0.05, "Config max_trade_sol should be 0.05"
assert config.max_daily_loss_sol == 0.2, "Config max_daily_loss_sol should be 0.2"
assert len(config.allowed_wallets) == 2, "Should have 2 allowed wallets"
print(f"  Config loaded: max_trade={config.max_trade_sol}, max_daily_loss={config.max_daily_loss_sol} (OK)")
print("")

# Initialize guard
print("[micro_live_smoke] Initializing MicroSafetyGuard...")
guard = MicroSafetyGuard(config)
limits = guard.get_limits()
print(f"  Guard limits: {limits} (OK)")
print("")

# Test 1: Large order should be rejected
print("[micro_live_smoke] Test 1: Large order rejection...")
large_amount = 100.0  # 100 SOL - way over limit
try:
    guard.validate_order(
        wallet_source="7nYhPEv7z5VnKMj4m6kV4qZz5v8p7Gw8q5dRt5k2w3xF",
        amount_in_sol=large_amount,
        current_exposure_sol=0.0,
        daily_loss_sol=0.0,
    )
    print("  ERROR: Large order should have been rejected!")
    sys.exit(1)
except SafetyViolationError as e:
    print(f"  Large order (100 SOL) rejected (OK)")
    assert "exceeds limit" in str(e), "Error should mention limit"

print("")

# Test 2: Unknown wallet should be rejected
print("[micro_live_smoke] Test 2: Unknown wallet rejection...")
unknown_wallet = "UnknownWallet123456789012345678901234567890"
try:
    guard.validate_order(
        wallet_source=unknown_wallet,
        amount_in_sol=0.05,
        current_exposure_sol=0.0,
        daily_loss_sol=0.0,
    )
    print("  ERROR: Unknown wallet should have been rejected!")
    sys.exit(1)
except SafetyViolationError as e:
    print(f"  Unknown wallet rejected (OK)")
    assert "not in allowlist" in str(e), "Error should mention allowlist"

print("")

# Test 3: Valid micro order should pass
print("[micro_live_smoke] Test 3: Valid micro order...")
valid_wallet = "7nYhPEv7z5VnKMj4m6kV4qZz5v8p7Gw8q5dRt5k2w3xF"
result = guard.validate_order(
    wallet_source=valid_wallet,
    amount_in_sol=0.05,
    current_exposure_sol=0.0,
    daily_loss_sol=0.0,
)
assert result == True, "Valid order should return True"
print(f"  Valid micro order passed (OK)")
print("")

# Test 4: Daily loss limit
print("[micro_live_smoke] Test 4: Daily loss limit...")
try:
    guard.validate_order(
        wallet_source=valid_wallet,
        amount_in_sol=0.05,
        current_exposure_sol=0.0,
        daily_loss_sol=0.5,  # At limit
    )
    print("  ERROR: Order with daily loss at limit should be rejected!")
    sys.exit(1)
except SafetyViolationError as e:
    print(f"  Daily loss limit enforced (OK)")

print("")

# Test 5: Exposure limit
print("[micro_live_smoke] Test 5: Exposure limit...")
try:
    guard.validate_order(
        wallet_source=valid_wallet,
        amount_in_sol=0.5,
        current_exposure_sol=0.6,  # Already near limit
        daily_loss_sol=0.0,
    )
    print("  ERROR: Order that exceeds exposure limit should be rejected!")
    sys.exit(1)
except SafetyViolationError as e:
    print(f"  Exposure limit enforced (OK)")

print("")

# Test 6: Config-bounded limits
print("[micro_live_smoke] Test 6: Config respects hard limits...")
# Try to set a config value higher than hard limit
bad_config = SafetyConfig(
    max_trade_sol=999.0,  # Way over MAX_MICRO_TRADE_SOL
    max_daily_loss_sol=0.2,
    allowed_wallets=[valid_wallet],
)
# Should be bounded to MAX_MICRO_TRADE_SOL
assert bad_config.max_trade_sol <= MAX_MICRO_TRADE_SOL, "Config should respect hard limit"
print(f"  Config bounded to hard limit: {bad_config.max_trade_sol} <= {MAX_MICRO_TRADE_SOL} (OK)")
print("")

print("[micro_live_smoke] All safety tests passed!")
print("[micro_live_smoke] OK")
PYTEST
