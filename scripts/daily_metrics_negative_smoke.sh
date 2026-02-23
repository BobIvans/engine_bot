#!/usr/bin/env bash
set -euo pipefail

# Daily metrics negative smoke test
# Tests: all-skip case (4 trade lines, but 0 trades pass through due to missing_snapshot and missing_wallet_profile)

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
        echo "ERROR: daily_metrics_negative_smoke_failed: expected $expr=$expected, got '$actual'" >&2
        exit 1
    fi
}

echo "[daily_metrics_negative_smoke] Testing all-skip case..." >&2

# Test: all-skip case (4 trade lines, 0 trades pass through)
run_pipeline \
    "integration/fixtures/config/daily_metrics_all_skip.yaml" \
    "integration/fixtures/trades.daily_metrics_all_skip.jsonl" \
    "integration/fixtures/token_snapshot.daily_metrics_all_skip.csv" \
    "integration/fixtures/wallet_profiles.daily_metrics_all_skip.csv" \
    "/tmp/daily_metrics_all_skip.json"

assert_py "/tmp/daily_metrics_all_skip.json" "d['daily_metrics']['schema_version']" "daily_metrics.v1"
assert_py "/tmp/daily_metrics_all_skip.json" "d['daily_metrics']['totals']['trades']" "0"
assert_py "/tmp/daily_metrics_all_skip.json" "d['daily_metrics']['days'][0]['trades']" "0"
# Total skipped should be 2 (2 BUY entries that failed sim_preflight)
total_skipped=$(( $(python3 - <<'PY'
import json
d = json.load(open('/tmp/daily_metrics_all_skip.json'))
s = d['daily_metrics']['days'][0]['skipped_by_reason']
print(s.get('missing_snapshot', 0) + s.get('missing_wallet_profile', 0) + s.get('ev_below_threshold', 0))
PY
) ))
if [ "$total_skipped" -eq 0 ]; then
    echo "ERROR: daily_metrics_negative_smoke_failed: expected some skips but got 0" >&2
    exit 1
fi

echo "[daily_metrics_negative_smoke] all-skip case passed (trades=0, skips=$total_skipped)" >&2

echo "[daily_metrics_negative_smoke] OK ✅" >&2
