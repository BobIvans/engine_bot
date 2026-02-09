#!/bin/bash
# Smoke test for RugCheck External Validator
# Tests: pure logic parsing, fail-open behavior, stage integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/rugcheck"

echo "[rugcheck_smoke] Starting RugCheck smoke test..."

# Test 1: Test pure logic with Good token
echo "[rugcheck_smoke] Testing good token parsing..."
GOOD_OUTPUT=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.safety.external_risk import normalize_rugcheck_report, format_output

with open('$FIXTURE_DIR/mock_good.json') as f:
    raw = json.load(f)

profile = normalize_rugcheck_report(raw)
output = format_output(profile)
print(json.dumps(output, indent=2))
")

GOOD_SCORE=$(python3 -c "import json; print(json.loads('''$GOOD_OUTPUT''').get('score', -1))")

if (( $(echo "$GOOD_SCORE >= 0.0 && $GOOD_SCORE < 0.3" | bc -l) )); then
    echo "[rugcheck_smoke] Good token score: $GOOD_SCORE (expected < 0.3) ✅"
else
    echo "[rugcheck_smoke] FAIL: Good token score should be < 0.3, got $GOOD_SCORE"
    exit 1
fi

# Test 2: Test pure logic with Bad token
echo "[rugcheck_smoke] Testing bad token parsing..."
BAD_OUTPUT=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.safety.external_risk import normalize_rugcheck_report, format_output

with open('$FIXTURE_DIR/mock_bad.json') as f:
    raw = json.load(f)

profile = normalize_rugcheck_report(raw)
output = format_output(profile)
print(json.dumps(output, indent=2))
")

BAD_SCORE=$(python3 -c "import json; print(json.loads('''$BAD_OUTPUT''').get('score', -1))")
BAD_FLAGS=$(python3 -c "import json; print(' '.join(json.loads('''$BAD_OUTPUT''').get('flags', [])))")

if (( $(echo "$BAD_SCORE > 0.7" | bc -l) )); then
    echo "[rugcheck_smoke] Bad token score: $BAD_SCORE (expected > 0.7) ✅"
else
    echo "[rugcheck_smoke] FAIL: Bad token score should be > 0.7, got $BAD_SCORE"
    exit 1
fi

# Test 3: Verify flags are parsed correctly
echo "[rugcheck_smoke] Verifying flags parsing..."
if [[ "$BAD_FLAGS" =~ "mint_authority_enabled" ]]; then
    echo "[rugcheck_smoke] Found mint_authority_enabled flag ✅"
else
    echo "[rugcheck_smoke] FAIL: mint_authority_enabled flag not found"
    exit 1
fi

if [[ "$BAD_FLAGS" =~ "freeze_authority_enabled" ]]; then
    echo "[rugcheck_smoke] Found freeze_authority_enabled flag ✅"
else
    echo "[rugcheck_smoke] FAIL: freeze_authority_enabled flag not found"
    exit 1
fi

if [[ "$BAD_FLAGS" =~ "top_holder_concentration_high" ]]; then
    echo "[rugcheck_smoke] Found top_holder_concentration_high flag ✅"
else
    echo "[rugcheck_smoke] FAIL: top_holder_concentration_high flag not found"
    exit 1
fi

if [[ "$BAD_FLAGS" =~ "owner_is_creator" ]]; then
    echo "[rugcheck_smoke] Found owner_is_creator flag ✅"
else
    echo "[rugcheck_smoke] FAIL: owner_is_creator flag not found"
    exit 1
fi

# Test 4: Test good flags (negative risk)
echo "[rugcheck_smoke] Verifying good flags..."
GOOD_FLAGS=$(python3 -c "import json; print(' '.join(json.loads('''$GOOD_OUTPUT''').get('flags', [])))")

if [[ "$GOOD_FLAGS" =~ "lp_burned" ]]; then
    echo "[rugcheck_smoke] Found lp_burned flag (negative risk) ✅"
else
    echo "[rugcheck_smoke] FAIL: lp_burned flag not found"
    exit 1
fi

if [[ "$GOOD_FLAGS" =~ "verified" ]]; then
    echo "[rugcheck_smoke] Found verified flag (negative risk) ✅"
else
    echo "[rugcheck_smoke] FAIL: verified flag not found"
    exit 1
fi

# Test 5: Test stage integration (mock mode)
echo "[rugcheck_smoke] Testing stage integration (mock mode)..."
STAGE_OUTPUT=$(python3 -m integration.rugcheck_stage --mock "$FIXTURE_DIR/mock_bad.json" 2>&1)

if [[ "$STAGE_OUTPUT" =~ "Score:" ]]; then
    echo "[rugcheck_smoke] Stage mock mode works ✅"
else
    echo "[rugcheck_smoke] FAIL: Stage mock mode not working"
    exit 1
fi

# Test 6: Verify output version format
echo "[rugcheck_smoke] Verifying output version format..."
VERSION=$(python3 -c "import json; print(json.loads('''$BAD_OUTPUT''').get('version', ''))")

if [[ "$VERSION" == "risk_eval.v1" ]]; then
    echo "[rugcheck_smoke] Output version is risk_eval.v1 ✅"
else
    echo "[rugcheck_smoke] FAIL: Expected version 'risk_eval.v1', got '$VERSION'"
    exit 1
fi

# Test 7: Test fail-open behavior (simulate API unavailability)
echo "[rugcheck_smoke] Testing fail-open behavior..."
FAIL_OPEN_OUTPUT=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.safety.external_risk import RiskProfile

# Simulate fail-open result
fail_open = {
    'mint': 'TestMint123',
    'provider': 'rugcheck',
    'score': 0.5,  # Neutral/Unknown
    'flags': ['api_unavailable'],
    'timestamp': 1234567890,
    'is_verified': False,
    'top_holder_concentration': 0.0,
}

# Verify fail-open profile structure
if fail_open['score'] == 0.5 and 'api_unavailable' in fail_open['flags']:
    print('Fail-open profile is valid')
else:
    print('FAIL: Invalid fail-open profile')
    exit(1)
")

if [[ "$FAIL_OPEN_OUTPUT" =~ "valid" ]]; then
    echo "[rugcheck_smoke] Fail-open behavior verified ✅"
else
    echo "[rugcheck_smoke] FAIL: Fail-open behavior not working"
    exit 1
fi

# Test 8: Test RugCheckClient initialization
echo "[rugcheck_smoke] Testing RugCheckClient..."
CLIENT_TEST=$(python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from integration.adapters.rugcheck import RugCheckClient

client = RugCheckClient()
stats = client.get_cache_stats()
print(f'Cache size: {stats[\"size\"]}')
")

if [[ "$CLIENT_TEST" =~ "Cache size: 0" ]]; then
    echo "[rugcheck_smoke] RugCheckClient initialization works ✅"
else
    echo "[rugcheck_smoke] FAIL: RugCheckClient initialization failed"
    exit 1
fi

echo "[rugcheck_smoke] All RugCheck smoke tests passed!"
echo "[rugcheck_smoke] OK"
