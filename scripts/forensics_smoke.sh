#!/bin/bash
# Smoke test for Trade Forensics Exporter
# Tests: pure logic assembly, stage integration, output format

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/forensics"
OUTPUT_FILE="/tmp/forensics_output.jsonl"

echo "[forensics_smoke] Starting Trade Forensics smoke test..."

# Clean up
rm -f "$OUTPUT_FILE"

# Test 1: Run forensics stage
echo "[forensics_smoke] Running forensics stage..."
python3 -m integration.forensics_stage \
    --signals "$FIXTURE_DIR/signals.jsonl" \
    --features "$FIXTURE_DIR/features.jsonl" \
    --execution "$FIXTURE_DIR/execution.jsonl" \
    --out "$OUTPUT_FILE" \
    --verbose

# Test 2: Verify output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "[forensics_smoke] FAIL: Output file not created"
    exit 1
fi

# Test 3: Verify output contains expected structure
echo "[forensics_smoke] Verifying output structure..."
BUNDLE_COUNT=$(wc -l < "$OUTPUT_FILE")

if [ "$BUNDLE_COUNT" -ne 2 ]; then
    echo "[forensics_smoke] FAIL: Expected 2 bundles, got $BUNDLE_COUNT"
    exit 1
fi

echo "[forensics_smoke] Found $BUNDLE_COUNT bundles ✅"

# Test 4: Verify first bundle has features and execution
echo "[forensics_smoke] Verifying bundle content..."
FIRST_BUNDLE=$(head -1 "$OUTPUT_FILE")

# Check for context.features
if [[ "$FIRST_BUNDLE" =~ "\"context\"" ]] && [[ "$FIRST_BUNDLE" =~ "\"features\"" ]]; then
    echo "[forensics_smoke] Found context.features ✅"
else
    echo "[forensics_smoke] FAIL: context.features not found"
    exit 1
fi

# Check for outcome.fill_status
if [[ "$FIRST_BUNDLE" =~ "\"outcome\"" ]] && [[ "$FIRST_BUNDLE" =~ "\"fill_status\"" ]]; then
    echo "[forensics_smoke] Found outcome.fill_status ✅"
else
    echo "[forensics_smoke] FAIL: outcome.fill_status not found"
    exit 1
fi

# Test 5: Verify version format
echo "[forensics_smoke] Verifying version format..."
VERSION=$(python3 -c "import json; print(json.loads(open('$OUTPUT_FILE').readline()).get('version', ''))")

if [[ "$VERSION" == "trade_forensics.v1" ]]; then
    echo "[forensics_smoke] Output version is trade_forensics.v1 ✅"
else
    echo "[forensics_smoke] FAIL: Expected version 'trade_forensics.v1', got '$VERSION'"
    exit 1
fi

# Test 6: Verify first bundle has filled status
echo "[forensics_smoke] Verifying fill_status..."
FILL_STATUS=$(python3 -c "import json; print(json.loads(open('$OUTPUT_FILE').readline()).get('outcome', {}).get('fill_status', 'null'))")

if [[ "$FILL_STATUS" == "filled" ]]; then
    echo "[forensics_smoke] Fill status is 'filled' ✅"
else
    echo "[forensics_smoke] FAIL: Expected fill_status 'filled', got '$FILL_STATUS'"
    exit 1
fi

# Test 7: Verify orphaned signal handling (S2 has no features/execution)
echo "[forensics_smoke] Verifying orphaned signal handling..."
METRICS=$(python3 -m integration.forensics_stage \
    --signals "$FIXTURE_DIR/signals.jsonl" \
    --features "$FIXTURE_DIR/features.jsonl" \
    --execution "$FIXTURE_DIR/execution.jsonl" \
    --out /tmp/metrics_test.jsonl 2>/dev/null)

ORPHANED=$(echo "$METRICS" | python3 -c "import json, sys; print(json.load(sys.stdin).get('orphaned_signals', -1))")

if [ "$ORPHANED" -eq 1 ]; then
    echo "[forensics_smoke] Orphaned signals correctly identified: $ORPHANED ✅"
else
    echo "[forensics_smoke] FAIL: Expected 1 orphaned signal, got $ORPHANED"
    exit 1
fi

# Test 8: Verify pure logic works standalone
echo "[forensics_smoke] Testing pure logic assembly..."
PURE_TEST=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.forensics.assembler import assemble_forensics

signal = {'signal_id': 'T1', 'score': 0.9, 'reason': 'test'}
features = {'volume_24h': 1000000}
execution = {'status': 'filled', 'price': 2.0}

bundle = assemble_forensics(signal, features, execution)
print(json.dumps(bundle))
")

if [[ "$PURE_TEST" =~ "\"context\"" ]] && [[ "$PURE_TEST" =~ "\"decision\"" ]]; then
    echo "[forensics_smoke] Pure logic assembly works ✅"
else
    echo "[forensics_smoke] FAIL: Pure logic assembly failed"
    exit 1
fi

# Test 9: Verify null handling for missing data
echo "[forensics_smoke] Testing null handling for missing data..."
NULL_TEST=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.forensics.assembler import assemble_forensics

signal = {'signal_id': 'T2', 'score': 0.5}

bundle = assemble_forensics(signal)
outcome = bundle.get('outcome', {})
fill_status = outcome.get('fill_status')

if fill_status is None:
    print('Null handling works')
else:
    print('FAIL: Expected null fill_status')
    exit(1)
")

if [[ "$NULL_TEST" =~ "Null handling works" ]]; then
    echo "[forensics_smoke] Null handling for missing data works ✅"
else
    echo "[forensics_smoke] FAIL: Null handling failed"
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_FILE" /tmp/metrics_test.jsonl

echo "[forensics_smoke] All Trade Forensics smoke tests passed!"
echo "[forensics_smoke] OK"
