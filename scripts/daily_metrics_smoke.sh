#!/usr/bin/env bash
set -euo pipefail

# Daily metrics smoke test (positive edge coverage)
# Tests: no_future_ticks and mixed_exits cases

run_pipeline() {
    local config="$1"
    local trades="$2"
    local token_snapshot="$3"
    local wallet_profiles="$4"
    local output_file="$5"
    
    # Capture stdout only
    python3 -m integration.paper_pipeline \
        --dry-run \
        --summary-json \
        --sim-preflight \
        --daily-metrics \
        --config "$config" \
        --trades-jsonl "$trades" \
        --token-snapshot "$token_snapshot" \
        --wallet-profiles "$wallet_profiles" \
        2>/dev/null > "$output_file"
}

# Python helper for JSON path assertions
assert_py() {
    local file="$1"
    local expr="$2"
    local expected="$3"
    local actual
    actual=$(python3 - <<PYEOF
import json
d = json.load(open('$file'))
result = $expr
print(result if result is not None else '')
PYEOF
)
    if [ "$actual" != "$expected" ]; then
        echo "ERROR: daily_metrics_smoke_failed: expected $expr=$expected, got '$actual'" >&2
        exit 1
    fi
}

echo "[daily_metrics_smoke] Testing no_future_ticks case..." >&2

# Test 1: no_future_ticks case (TIME exit with pnl=0)
run_pipeline \
    "integration/fixtures/config/daily_metrics_no_future_ticks.yaml" \
    "integration/fixtures/trades.daily_metrics_no_future_ticks.jsonl" \
    "integration/fixtures/token_snapshot.daily_metrics_no_future_ticks.csv" \
    "integration/fixtures/wallet_profiles.daily_metrics_no_future_ticks.csv" \
    "/tmp/daily_metrics_no_future_ticks.json"

assert_py "/tmp/daily_metrics_no_future_ticks.json" "d['daily_metrics']['schema_version']" "daily_metrics.v1"
assert_py "/tmp/daily_metrics_no_future_ticks.json" "d['daily_metrics']['totals']['trades']" "1"
# exit_reason_counts is in days[0], not totals
assert_py "/tmp/daily_metrics_no_future_ticks.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['TP']" "0"
assert_py "/tmp/daily_metrics_no_future_ticks.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['SL']" "0"
assert_py "/tmp/daily_metrics_no_future_ticks.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['TIME']" "1"

echo "[daily_metrics_smoke] no_future_ticks case passed" >&2

echo "[daily_metrics_smoke] Testing mixed_exits case..." >&2

# Test 2: mixed_exits case (TP + SL + TIME)
run_pipeline \
    "integration/fixtures/config/daily_metrics_mixed_exits.yaml" \
    "integration/fixtures/trades.daily_metrics_mixed_exits.jsonl" \
    "integration/fixtures/token_snapshot.daily_metrics_mixed_exits.csv" \
    "integration/fixtures/wallet_profiles.daily_metrics_mixed_exits.csv" \
    "/tmp/daily_metrics_mixed_exits.json"

assert_py "/tmp/daily_metrics_mixed_exits.json" "d['daily_metrics']['schema_version']" "daily_metrics.v1"
assert_py "/tmp/daily_metrics_mixed_exits.json" "d['daily_metrics']['totals']['trades']" "3"
# exit_reason_counts is in days[0], not totals
assert_py "/tmp/daily_metrics_mixed_exits.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['TP']" "1"
assert_py "/tmp/daily_metrics_mixed_exits.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['SL']" "1"
assert_py "/tmp/daily_metrics_mixed_exits.json" "d['daily_metrics']['days'][0]['exit_reason_counts']['TIME']" "1"

echo "[daily_metrics_smoke] mixed_exits case passed" >&2

echo "[daily_metrics_smoke] OK ✅" >&2
