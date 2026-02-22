#!/bin/bash
# scripts/decision_smoke.sh
# Decision logic smoke test (robust, CI-safe)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIOS_FILE="$PROJECT_ROOT/integration/fixtures/decision/scenarios.jsonl"

echo "[decision_smoke] Running decision logic smoke tests..." >&2

if [ ! -f "$SCENARIOS_FILE" ]; then
  echo "[decision_smoke] ERROR: scenarios file not found at $SCENARIOS_FILE" >&2
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

# Run python once; capture all output
OUT="$(python3 - <<PY
import json, sys
sys.path.insert(0, "$PROJECT_ROOT")

from integration.decision_stage import DecisionStage

stage = DecisionStage()
results = stage.process_scenarios("$SCENARIOS_FILE")

expected = {}
with open("$SCENARIOS_FILE", "r") as f:
    for line in f:
        line=line.strip()
        if not line:
            continue
        obj=json.loads(line)
        expected[obj["id"]] = obj

passed = 0
failed = 0

for scenario_id, signal in results.items():
    exp = expected.get(scenario_id, {})
    exp_decision = exp.get("expected_decision", "SKIP")
    exp_reason = exp.get("expected_reason")
    exp_mode = exp.get("expected_mode")

    if signal.decision.value != exp_decision:
        print(f"FAIL:{scenario_id}:decision:{signal.decision.value}:{exp_decision}", file=sys.stderr)
        failed += 1
        continue

    if exp_decision == "SKIP" and exp_reason:
        if signal.reason != exp_reason:
            print(f"FAIL:{scenario_id}:reason:{signal.reason}:{exp_reason}", file=sys.stderr)
            failed += 1
            continue

    if exp_decision == "ENTER" and exp_mode:
        if signal.mode.value != exp_mode:
            print(f"FAIL:{scenario_id}:mode:{signal.mode.value}:{exp_mode}", file=sys.stderr)
            failed += 1
            continue

    # optional debug
    if exp_decision == "ENTER":
        print(f"PASS:{scenario_id}:regime={signal.regime}:mode={signal.mode.value}")

    passed += 1

print(f"RESULTS:{passed}:{failed}")
PY
)"

# echo python output (both stderr already shown by runner; stdout captured in OUT)
# But we still need RESULTS line from OUT:
RESULTS_LINE="$(printf "%s\n" "$OUT" | tail -n 1)"
PASS_COUNT="$(printf "%s" "$RESULTS_LINE" | cut -d: -f2)"
FAIL_COUNT="$(printf "%s" "$RESULTS_LINE" | cut -d: -f3)"

echo "[decision_smoke] Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed" >&2

if [ "${FAIL_COUNT}" -eq 0 ]; then
  echo "[decision_smoke] OK" >&2
  exit 0
else
  echo "[decision_smoke] FAIL (${FAIL_COUNT} failed)" >&2
  exit 1
fi
