#!/bin/bash
# scripts/trailing_dynamic_smoke.sh
# PR-Z.3 Trailing Stop Dynamic Adjustment - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
FIXTURES_DIR="$ROOT_DIR/integration/fixtures/trailing"

echo "[trailing_dynamic_smoke] Starting PR-Z.3 smoke tests..."

# Test 1: Verify module imports
echo "[trailing_dynamic_smoke] Testing imports..."
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from config.runtime_schema import RuntimeConfig
from execution.market_features import MarketContext
from execution.trailing_adjuster import TrailingAdjuster, create_trailing_adjuster
print('[trailing_dynamic_smoke] Imports OK')
"

# Test 2: Create test config with dynamic trailing parameters
python3 -c "
import sys
sys.path.insert(0, '$ROOT_DIR')
from config.runtime_schema import RuntimeConfig
from execution.market_features import MarketContext
from execution.trailing_adjuster import TrailingAdjuster

# Create config with dynamic trailing parameters
config = RuntimeConfig(
    dynamic_trailing_enabled=True,
    trailing_base_distance_bps=150,
    trailing_volatility_multiplier=1.8,
    trailing_volume_multiplier=0.9,
    trailing_max_distance_bps=500,
    trailing_rv_threshold_high=0.08,
    trailing_rv_threshold_low=0.03,
    trailing_volume_confirm_threshold=1.5
)

print('[trailing_dynamic_smoke] Config created OK')

# Create adjuster
adjuster = TrailingAdjuster(config)
print('[trailing_dynamic_smoke] TrailingAdjuster instantiated OK')
"

# Test 3: Load fixtures
echo "[trailing_dynamic_smoke] Loading fixtures..."
if [ ! -f "$FIXTURES_DIR/market_context_sequence.json" ]; then
    echo "[trailing_dynamic_smoke] ERROR: market_context_sequence.json not found"
    exit 1
fi
if [ ! -f "$FIXTURES_DIR/expected_trailing_distances.json" ]; then
    echo "[trailing_dynamic_smoke] ERROR: expected_trailing_distances.json not found"
    exit 1
fi
echo "[trailing_dynamic_smoke] Fixtures found OK"

# Test 4: Run adapter on sequence with logging
echo "[trailing_dynamic_smoke] Running TrailingAdjuster on market sequence..."
python3 "$SCRIPT_DIR/trailing_dynamic_test.py"

echo "[trailing_dynamic_smoke] All PR-Z.3 smoke tests passed!"
echo "[trailing_dynamic_smoke] OK"
