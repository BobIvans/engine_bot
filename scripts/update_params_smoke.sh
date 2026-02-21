#!/usr/bin/env bash
set -eo pipefail
# Smoke test for PR-Q.1 Stats Feedback Loop.
# Tests the update_params.py script with fixtures.
# NOTE: This test runs in MOCK mode - no real network/execution.

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from script
project_root="$(dirname "$SCRIPT_DIR")"

echo "project_root: $project_root" >&2

# Add project to PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}:$project_root"

# Define fixture paths
FIXTURE_DIR="$project_root/integration/fixtures/update_params"
METRICS_FILE="$FIXTURE_DIR/daily_metrics_sample.jsonl"
BEFORE_FILE="$FIXTURE_DIR/params_base_before.yaml"
EXPECTED_FILE="$FIXTURE_DIR/expected_params_base_after.yaml"
OUT_FILE="$FIXTURE_DIR/params_updated.yaml"

# Run update_params.py
echo "[update_params_smoke] Running update_params.py on fixtures..." >&2

cd "$project_root"

# Run the update script with min_days_required=1 to override the default
python3 "$project_root/strategy/optimization/update_params.py" \
    --metrics "$METRICS_FILE" \
    --config "$BEFORE_FILE" \
    --output "$OUT_FILE" \
    --lookback-days 30 \
    2>&1

UPDATE_EXIT=$?

if [ $UPDATE_EXIT -ne 0 ]; then
    echo "[update_params_smoke] FAILED: update_params.py exited with code $UPDATE_EXIT" >&2
    exit 1
fi

# Check if output file was created
if [ ! -f "$OUT_FILE" ]; then
    echo "[update_params_smoke] FAILED: Output file not created" >&2
    exit 1
fi

# Compare with expected output
echo "[update_params_smoke] Comparing output with expected..." >&2

python3 - "$EXPECTED_FILE" "$OUT_FILE" << 'PYTHON_SCRIPT'
import sys
import yaml

expected_file = sys.argv[1]
out_file = sys.argv[2]

with open(expected_file) as f:
    expected = yaml.safe_load(f)

with open(out_file) as f:
    actual = yaml.safe_load(f)

# Compare payoff_mu_win
expected_win = expected.get("payoff_mu_win", {})
actual_win = actual.get("payoff_mu_win", {})

for mode in ["U", "S", "M", "L"]:
    exp = expected_win.get(mode)
    act = actual_win.get(mode)
    if exp is None or act is None:
        print(f"[update_params_smoke] FAILED: payoff_mu_win[{mode}] missing", file=sys.stderr)
        sys.exit(1)
    if abs(exp - act) > 0.0001:
        print(f"[update_params_smoke] FAILED: payoff_mu_win[{mode}] expected {exp}, got {act}", file=sys.stderr)
        sys.exit(1)
    print(f"[update_params_smoke] payoff_mu_win[{mode}] = {act} (OK)", file=sys.stderr)

# Compare payoff_mu_loss
expected_loss = expected.get("payoff_mu_loss", {})
actual_loss = actual.get("payoff_mu_loss", {})

for mode in ["U", "S", "M", "L"]:
    exp = expected_loss.get(mode)
    act = actual_loss.get(mode)
    if exp is None or act is None:
        print(f"[update_params_smoke] FAILED: payoff_mu_loss[{mode}] missing", file=sys.stderr)
        sys.exit(1)
    if abs(exp - act) > 0.0001:
        print(f"[update_params_smoke] FAILED: payoff_mu_loss[{mode}] expected {exp}, got {act}", file=sys.stderr)
        sys.exit(1)
    print(f"[update_params_smoke] payoff_mu_loss[{mode}] = {act} (OK)", file=sys.stderr)

print("[update_params_smoke] All values match expected output", file=sys.stderr)
PYTHON_SCRIPT

if [ $? -ne 0 ]; then
    exit 1
fi

# Cleanup
rm -f "$OUT_FILE"

echo "[update_params_smoke] OK" >&2
exit 0
