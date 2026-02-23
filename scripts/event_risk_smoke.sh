#!/bin/bash
# PR-PM.3 Event Risk Aggregator Smoke Test
# Tests core functionality of event risk detection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_PATH="$PROJECT_ROOT/integration/fixtures/sentiment/polymarket_sample_events.json"
OUTPUT_PATH="/tmp/event_risk_output.json"

echo "=== PR-PM.3 Event Risk Aggregator Smoke Test ==="

# Check fixture exists
if [ ! -f "$FIXTURE_PATH" ]; then
    echo "ERROR: Fixture not found at $FIXTURE_PATH"
    exit 1
fi
echo "[PASS] Fixture found: $FIXTURE_PATH"

# Check Python module imports
echo ""
echo "Testing Python imports..."
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from analysis.event_risk import (
    detect_event_type,
    compute_days_to_resolution,
    detect_event_risk,
    EventRiskTimeline,
    PolymarketSnapshotInput,
)
print('[PASS] All imports successful')
"

# Test event type detection
echo ""
echo "Testing event type detection..."
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from analysis.event_risk import detect_event_type, CRITICAL_TYPES

tests = [
    ('Will Trump win the 2024 election?', 'election'),
    ('Will SEC approve Bitcoin ETF?', 'etf'),
    ('Will SEC reject this token?', 'regulatory'),
    ('Will FOMC cut rates?', 'fed'),
    ('Will US enter recession?', 'macro'),
    ('Random market question', 'other'),
]

all_passed = True
for question, expected in tests:
    result = detect_event_type(question)
    status = 'PASS' if result == expected else 'FAIL'
    if status == 'FAIL':
        all_passed = False
    print(f'  [{status}] \"{question}\" -> {result} (expected: {expected})')

if not all_passed:
    sys.exit(1)
print('[PASS] Event type detection works correctly')
"

# Test days calculation
echo ""
echo "Testing days to resolution calculation..."
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from analysis.event_risk import compute_days_to_resolution
from datetime import datetime

# Test: 7 days from now
now_ms = int(datetime.now().timestamp() * 1000)
seven_days_ms = 7 * 24 * 3600 * 1000
result = compute_days_to_resolution(now_ms + seven_days_ms, now_ms)
assert result == 7, f'Expected 7, got {result}'
print(f'  [PASS] 7 days in future: {result} days')

# Test: 3 days ago
result = compute_days_to_resolution(now_ms - 3 * 24 * 3600 * 1000, now_ms)
assert result == -3, f'Expected -3, got {result}'
print(f'  [PASS] 3 days ago: {result} days')

print('[PASS] Days calculation works correctly')
"

# Test end-to-end pipeline
echo ""
echo "Testing end-to-end pipeline..."
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from ingestion.pipelines.event_risk_pipeline import EventRiskPipeline
from datetime import datetime

pipeline = EventRiskPipeline(
    snapshot_path='$FIXTURE_PATH',
    output_path='$OUTPUT_PATH',
    now_ts_ms=int(datetime.now().timestamp() * 1000),
)

timeline = pipeline.run()
print(f'  Result: high_risk={timeline.high_event_risk}, days={timeline.days_to_resolution}, type={timeline.event_type}')
assert timeline.event_type in ['election', 'etf', 'regulatory', 'fed', 'macro', 'other']
print('[PASS] End-to-end pipeline executed')
"

# Verify output
if [ -f "$OUTPUT_PATH" ]; then
    echo ""
    echo "Verifying output file..."
    python3 -c "
import sys
import json
with open('$OUTPUT_PATH') as f:
    data = json.load(f)
required = ['ts', 'high_event_risk', 'days_to_resolution', 'event_type', 'event_name', 'source_snapshot_id']
for key in required:
    assert key in data, f'Missing key: {key}'
print(f'  [PASS] Output file valid: {json.dumps(data, indent=2)}')
"
    rm -f "$OUTPUT_PATH"
else
    echo "WARNING: Output file not created at $OUTPUT_PATH"
fi

echo ""
echo "=== All smoke tests passed ==="
