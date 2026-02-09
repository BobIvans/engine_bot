#!/bin/bash
#
# Decision Logic Smoke Test
# Validates CopyScalpStrategy against test scenarios
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIOS_FILE="$PROJECT_ROOT/integration/fixtures/decision/scenarios.jsonl"
PYTHON_PATH="$PROJECT_ROOT"

echo "[decision_smoke] Running decision logic smoke tests..."

# Check if scenarios file exists
if [ ! -f "$SCENARIOS_FILE" ]; then
    echo "[decision_smoke] ERROR: scenarios file not found at $SCENARIOS_FILE" >&2
    exit 1
fi

# Add project root to PYTHONPATH
export PYTHONPATH="$PYTHON_PATH:$PYTHONPATH"

PASS_COUNT=0
FAIL_COUNT=0

# Run decision stage on scenarios
echo "[decision_smoke] Processing scenarios..." >&2
python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
import json
from integration.decision_stage import DecisionStage
from strategy.logic import Decision

stage = DecisionStage()
results = stage.process_scenarios('$SCENARIOS_FILE')

# Load expected results
with open('$SCENARIOS_FILE', 'r') as f:
    expected = {json.loads(line)['id']: json.loads(line) for line in f if line.strip()}

passed = 0
failed = 0

for scenario_id, signal in results.items():
    exp = expected.get(scenario_id, {})
    exp_decision = exp.get('expected_decision', 'SKIP')
    exp_reason = exp.get('expected_reason')
    exp_mode = exp.get('expected_mode')
    
    # Check decision
    if signal.decision.value != exp_decision:
        print(f'FAIL:{scenario_id}:decision:{signal.decision.value}:{exp_decision}', file=sys.stderr)
        failed += 1
        continue
    
    # Check reason for SKIP
    if exp_decision == 'SKIP' and exp_reason:
        if signal.reason != exp_reason:
            print(f'FAIL:{scenario_id}:reason:{signal.reason}:{exp_reason}', file=sys.stderr)
            failed += 1
            continue
    
    # Check mode for ENTER
    if exp_decision == 'ENTER' and exp_mode:
        if signal.mode.value != exp_mode:
            print(f'FAIL:{scenario_id}:mode:{signal.mode.value}:{exp_mode}', file=sys.stderr)
            failed += 1
            continue
    
    # Also verify regime affects threshold (log for debugging)
    if exp_decision == 'ENTER' and signal.regime:
        print(f'PASS:{scenario_id}:regime={signal.regime}:mode={signal.mode.value}')
    
    passed += 1

print(f'RESULTS:{passed}:{failed}')
" 2>&1 | while read -r line; do
    if [[ "$line" == RESULTS:* ]]; then
        echo "[decision_smoke] Scenarios processed"
        PASS_COUNT=$(echo "$line" | cut -d':' -f2)
        FAIL_COUNT=$(echo "$line" | cut -d':' -f3)
    elif [[ "$line" == PASS:* ]]; then
        scenario=$(echo "$line" | cut -d':' -f2)
        details=$(echo "$line" | cut -d':' -f3-)
        echo "[decision_smoke] Scenario $scenario... PASS ($details)"
        ((PASS_COUNT++))
    elif [[ "$line" == FAIL:* ]]; then
        scenario=$(echo "$line" | cut -d':' -f2)
        check=$(echo "$line" | cut -d':' -f3)
        actual=$(echo "$line" | cut -d':' -f4)
        expected=$(echo "$line" | cut -d':' -f5)
        echo "[decision_smoke] Scenario $scenario... FAIL ($check: got $actual, expected $expected)" >&2
        ((FAIL_COUNT++))
    else
        # Echo debug info
        echo "[decision_smoke] $line" >&2
    fi
done

# Summary
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "[decision_smoke] OK"
    exit 0
else
    echo "[decision_smoke] FAIL - $FAIL_COUNT scenarios failed" >&2
    exit 1
fi
