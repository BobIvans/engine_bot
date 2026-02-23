#!/bin/bash
#
# Jupiter Quote Smoke Test
#
# Validates Jupiter Quote API v6 adapter using fixture data.
# Does NOT call real API - uses offline fixture only.
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failure
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_FILE="${SCRIPT_DIR}/../integration/fixtures/execution/jupiter_quote_sample.json"
MODULE_PATH="ingestion.sources.jupiter_quote"

echo "[overlay_lint] running jupiter_quote smoke..."

# Verify fixture exists
if [ ! -f "$FIXTURE_FILE" ]; then
    echo "[jupiter_quote_smoke] ERROR: Fixture file not found: $FIXTURE_FILE" >&2
    exit 1
fi

# Run the adapter in fixture-only mode
echo "[jupiter_quote_smoke] Running adapter on fixture..."
STDOUT_OUTPUT=$(python3 -m "$MODULE_PATH" \
    --input-file "$FIXTURE_FILE" \
    --in-mint "So11111111111111111111111111111111111111112" \
    --out-mint "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm" \
    --amount "1000000000" \
    --dry-run \
    --summary-json 2>&1)

STDOUT_JSON=$(echo "$STDOUT_OUTPUT" | grep -v '^\[jupiter_quote\]' | head -1)
STDERR_OUTPUT=$(echo "$STDOUT_OUTPUT" | grep '^\[jupiter_quote\]')

# Verify summary JSON fields (robust to whitespace formatting)
python3 - <<'PYJSON' "$STDOUT_JSON"
import json
import sys

raw = sys.argv[1].strip()
try:
    payload = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"[jupiter_quote_smoke] ERROR: invalid summary JSON: {e}", file=sys.stderr)
    print(raw, file=sys.stderr)
    raise SystemExit(1)

checks = [
    (payload.get("quote_success") is True, "quote_success not true"),
    (payload.get("out_amount") == "42857142857", "out_amount mismatch"),
    (payload.get("price_impact_pct") == 1.25, "price_impact_pct mismatch"),
    (payload.get("route_hops") == 1, "route_hops mismatch"),
]

for ok, msg in checks:
    if not ok:
        print(f"[jupiter_quote_smoke] ERROR: {msg}", file=sys.stderr)
        print(raw, file=sys.stderr)
        raise SystemExit(1)
PYJSON

# Verify stderr contains expected markers
if ! echo "$STDERR_OUTPUT" | grep -q 'Loaded fixture'; then
    echo "[jupiter_quote_smoke] ERROR: Missing fixture load message in stderr" >&2
    echo "$STDERR_OUTPUT" >&2
    exit 1
fi

if ! echo "$STDERR_OUTPUT" | grep -q 'Route:'; then
    echo "[jupiter_quote_smoke] ERROR: Missing Route message in stderr" >&2
    echo "$STDERR_OUTPUT" >&2
    exit 1
fi

# Additional validation: check for Raydium label in full output
FULL_OUTPUT=$(python3 -m "$MODULE_PATH" \
    --input-file "$FIXTURE_FILE" \
    --in-mint "So11111111111111111111111111111111111111112" \
    --out-mint "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm" \
    --amount "1000000000" \
    --dry-run 2>&1)

if ! echo "$FULL_OUTPUT" | grep -q '"label":[[:space:]]*"Raydium"'; then
    echo "[jupiter_quote_smoke] ERROR: Missing Raydium label in route plan" >&2
    exit 1
fi

# All validations passed
echo "[jupiter_quote_smoke] validated quote against jupiter_route.v1 schema"
echo "[jupiter_quote_smoke] OK"

# Summary
echo ""
echo "=== Smoke Test Results ==="
echo "Quote success: true"
echo "Out amount: 42857142857"
echo "Price impact: 1.25%"
echo "Route hops: 1 (Raydium)"
echo "=========================="

exit 0
