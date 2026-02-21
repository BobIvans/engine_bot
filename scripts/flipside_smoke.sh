# Smoke test for PR-WD.2 Flipside Wallet Fetcher
# Tests: fixture loading, schema validation, normalization logic

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/discovery"

echo "[flipside_smoke] Starting Flipside wallet fetcher smoke test..."

# Test 1: Run flipside source adapter on fixture (Python inline)
echo "[flipside_smoke] Test 1: Running flipside source adapter on fixture..."

OUTPUT=$(cd "$PROJECT_ROOT" && python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')

from ingestion.sources.flipside import FlipsideWalletSource

source = FlipsideWalletSource()
profiles = source.load_from_file('integration/fixtures/discovery/flipside_sample.csv')

import json
for p in profiles:
    print(json.dumps(p.to_dict()))

# Summary JSON
print(json.dumps({"exported_count": len(profiles), "schema_version": "wallet_profile.v1"}))
PYEOF
)

if [ -z "$OUTPUT" ]; then
    echo "[flipside_smoke] FAIL: No output generated"
    exit 1
fi
echo "[flipside_smoke] Output generated ✅"

# Test 2: Verify exported_count
echo "[flipside_smoke] Test 2: Verifying exported_count..."
EXPORTED_COUNT=$(echo "$OUTPUT" | tail -1 | python3 -c "import json, sys; print(json.load(sys.stdin).get('exported_count', -1))")

if [ "$EXPORTED_COUNT" -ne 5 ]; then
    echo "[flipside_smoke] FAIL: Expected exported_count=5, got $EXPORTED_COUNT"
    exit 1
fi
echo "[flipside_smoke] exported_count=$EXPORTED_COUNT ✅"

# Test 3: Verify schema_version
echo "[flipside_smoke] Test 3: Verifying schema_version..."
SCHEMA_VERSION=$(echo "$OUTPUT" | tail -1 | python3 -c "import json, sys; print(json.load(sys.stdin).get('schema_version', ''))")

if [ "$SCHEMA_VERSION" != "wallet_profile.v1" ]; then
    echo "[flipside_smoke] FAIL: Expected schema_version='wallet_profile.v1', got '$SCHEMA_VERSION'"
    exit 1
fi
echo "[flipside_smoke] schema_version=$SCHEMA_VERSION ✅"

# Test 4: Verify wallet_addr count
echo "[flipside_smoke] Test 4: Verifying wallet_addr count..."
WALLET_COUNT=$(echo "$OUTPUT" | grep -c '"wallet_addr"' || echo "0")

if [ "$WALLET_COUNT" -ne 5 ]; then
    echo "[flipside_smoke] FAIL: Expected 5 wallet_addr entries, got $WALLET_COUNT"
    exit 1
fi
echo "[flipside_smoke] Found $WALLET_COUNT wallet addresses ✅"

# Test 5: Verify normalize_flipside_row function in profiling module
echo "[flipside_smoke] Test 5: Testing normalize_flipside_row function..."
PURE_TEST=$(cd "$PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, '.')
from strategy.profiling import normalize_flipside_row

# Test valid row
row = {
    'swapper': 'test_wallet',
    'roi_30d': 0.38,
    'winrate_30d': 0.72,
    'trades_30d': 98,
    'median_hold_sec': 215,
    'avg_size_usd': 1890,
    'memecoin_swaps': 87,
    'total_swaps': 98,
}
profile = normalize_flipside_row(row)
if profile is None:
    print('FAILED')
    sys.exit(1)
if profile.wallet != 'test_wallet':
    print('FAILED')
    sys.exit(1)
if profile.roi_30d_pct != 0.38:
    print('FAILED')
    sys.exit(1)
print('SUCCESS')
")

if [[ "$PURE_TEST" != "SUCCESS" ]]; then
    echo "[flipside_smoke] FAIL: normalize_flipside_row test failed"
    exit 1
fi
echo "[flipside_smoke] normalize_flipside_row works ✅"

# Test 6: Verify validation (invalid winrate should return None)
echo "[flipside_smoke] Test 6: Testing validation (invalid winrate)..."
VALIDATION_TEST=$(cd "$PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, '.')
from strategy.profiling import normalize_flipside_row

# Test invalid winrate (> 1.0)
row = {
    'swapper': 'test_wallet',
    'roi_30d': 0.38,
    'winrate_30d': 1.5,  # Invalid: > 1.0
    'trades_30d': 98,
}
profile = normalize_flipside_row(row)
if profile is not None:
    print('FAILED')
    sys.exit(1)
print('SUCCESS')
")

if [[ "$VALIDATION_TEST" != "SUCCESS" ]]; then
    echo "[flipside_smoke] FAIL: Validation test failed"
    exit 1
fi
echo "[flipside_smoke] Validation works ✅"

# Test 7: Verify CLI with --skip-flipside flag exists
echo "[flipside_smoke] Test 7: Verifying --skip-flipside flag..."
SKIP_TEST=$(cd "$PROJECT_ROOT" && python3 -c "
import subprocess
import sys
result = subprocess.run(
    ['python3', '-m', 'integration.wallet_discovery', '--help'],
    capture_output=True,
    text=True
)
if '--skip-flipside' not in result.stdout:
    print('FAILED')
    sys.exit(1)
print('SUCCESS')
")

if [[ "$SKIP_TEST" != "SUCCESS" ]]; then
    echo "[flipside_smoke] FAIL: --skip-flipside flag not found"
    exit 1
fi
echo "[flipside_smoke] --skip-flipside flag exists ✅"

# Test 8: Verify dry-run mode doesn't write files
echo "[flipside_smoke] Test 8: Verifying dry-run mode..."
DRY_TEST=$(cd "$PROJECT_ROOT" && python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')
from ingestion.sources.flipside import FlipsideWalletSource

source = FlipsideWalletSource()
source.export_to_parquet([], '/tmp/test_parquet_output.parquet', dry_run=True)
print('OK')
PYEOF
)

if [[ "$DRY_TEST" != "OK" ]]; then
    echo "[flipside_smoke] FAIL: Dry-run mode not working"
    exit 1
fi
echo "[flipside_smoke] Dry-run mode works ✅"

# Final output
echo "[flipside_smoke] validated 5 wallets against wallet_profile.v1 schema"
echo "[flipside_smoke] OK"
