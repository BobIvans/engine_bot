#!/bin/bash
#
# Aggressive Switch Smoke Test
# Validates aggressive switch logic against test scenarios
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_PATH="$PROJECT_ROOT"

echo "[aggr_switch_smoke] Running aggressive switch smoke tests..."

# Add project root to PYTHONPATH
export PYTHONPATH="$PYTHON_PATH:$PYTHONPATH"

# Run aggr switch stage on scenarios and capture output
python3 -c "
import sys
sys.path.insert(0, '$PYTHON_PATH')
from integration.aggr_switch_stage import AggrSwitchStage

stage = AggrSwitchStage()
results = stage.process_scenarios('$PROJECT_ROOT/integration/fixtures/aggr_switch/scenarios.jsonl')

passed = 0
failed = 0

for scenario_id, result in results.items():
    expected_decision = result.get('expected_decision')
    expected_reason = result.get('expected_reason')
    
    actual_decision = result.get('new_mode')
    actual_reason = result.get('reason')
    
    # Check decision and reason
    if actual_decision == expected_decision and actual_reason == expected_reason:
        print(f'[aggr_switch_smoke] Scenario {scenario_id}... PASS (new_mode={actual_decision})')
        passed += 1
    else:
        print(f'[aggr_switch_smoke] Scenario {scenario_id}... FAIL', file=sys.stderr)
        if actual_decision != expected_decision:
            print(f'  decision: got {actual_decision}, expected {expected_decision}', file=sys.stderr)
        if actual_reason != expected_reason:
            print(f'  reason: got {actual_reason}, expected {expected_reason}', file=sys.stderr)
        failed += 1

print(f'[aggr_switch_smoke] Results: {passed} passed, {failed} failed')

if failed > 0:
    print('[aggr_switch_smoke] FAIL', file=sys.stderr)
    sys.exit(1)

print('[aggr_switch_smoke] OK')
"
