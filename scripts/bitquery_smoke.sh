#!/bin/bash
# Smoke test for Bitquery GraphQL Adapter
# Tests: Pipeline integration, fixture loading, normalization, rejection logic

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_PATH="$PROJECT_ROOT/integration/fixtures/bitquery/graphql_response_sample.json"
# Pipeline writes rejects to --signals-out if we want? No, pipeline writes rejects mostly to logs or DB.
# But we can check summary JSON.

SUMMARY_JSON="/tmp/bitquery_summary.json"

echo "[bitquery_smoke] Starting Bitquery adapter smoke test..." >&2

# Clean up
rm -f "$SUMMARY_JSON"

# Run pipeline with Bitquery source
# We use --summary-json to get stats
# We use --dry-run to avoid DB writes
echo "[bitquery_smoke] Running pipeline with Bitquery fixture..." >&2
python3 -m integration.paper_pipeline \
    --use-bitquery \
    --bitquery-source "$FIXTURE_PATH" \
    --summary-json \
    --dry-run \
     2> /tmp/bitquery_stderr.log > "$SUMMARY_JSON"

# Verify stdout JSON
if [ ! -s "$SUMMARY_JSON" ]; then
    echo "[bitquery_smoke] FAIL: No summary JSON produced" >&2
    cat /tmp/bitquery_stderr.log >&2
    exit 1
fi

# Parse summary
TOTAL=$(python3 -c "import json; print(json.load(open('$SUMMARY_JSON'))['counts']['total_lines'])")
NORMALIZED=$(python3 -c "import json; print(json.load(open('$SUMMARY_JSON'))['counts']['normalized_ok'])")
REJECTED=$(python3 -c "import json; print(json.load(open('$SUMMARY_JSON'))['counts']['rejected_by_normalizer'])")

# We expect 4 total trades in fixture:
# 1. Valid
# 2. Valid
# 3. Invalid Price (amountOut=0)
# 4. Invalid Schema (empty swaps)
# So: Total=4, Normalized=2, Rejected=2

if [ "$TOTAL" != "4" ]; then
    echo "[bitquery_smoke] FAIL: Expected 4 total lines, got $TOTAL" >&2
    exit 1
fi

if [ "$NORMALIZED" != "2" ]; then
    echo "[bitquery_smoke] FAIL: Expected 2 normalized OK, got $NORMALIZED" >&2
    exit 1
fi

if [ "$REJECTED" != "2" ]; then
    echo "[bitquery_smoke] FAIL: Expected 2 rejected, got $REJECTED" >&2
    exit 1
fi

echo "[bitquery_smoke] Counts verified (Total: $TOTAL, OK: $NORMALIZED, Rejected: $REJECTED) ✓" >&2

# Verify specific rejection reasons in stderr (pipeline logs rejects to stderr in dry-run usually? No, it writes to DB or just counts)
# But we added `yield {"_reject": True...}`
# The pipeline logs rejects to DB.
# In --dry-run, it logs to stderr?
# Look at paper_pipeline:
# if item.get("_reject"):
#    ...
#    if runner is not None: insert_trade_reject(...)
# It doesn't print to stderr unless we add logging there.
# But we verified counts via summary, which is good enough for smoke.
# We can also check if we can see "REJECT_BITQUERY_SCHEMA_MISMATCH" in summary?
# The summary usually aggregates counts.
# Let's inspect the summary structure if we need more detail.
# But the counters match, so we are confident.

echo "[bitquery_smoke] OK ✅"
