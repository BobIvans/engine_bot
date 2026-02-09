#!/bin/bash
# scripts/dune_smoke.sh

set -e

echo "[overlay_lint] running dune smoke..."

cd "$(dirname "$0")/.."

# Run smoke test with dry-run and summary-json
OUTPUT=$(python3 -m integration.dune_source \
    --input-file integration/fixtures/discovery/dune_export_sample.csv \
    --dry-run \
    --summary-json 2>/dev/null)

# Check summary JSON output
if [ -z "$OUTPUT" ]; then
    echo "[dune_smoke] FAILED: No JSON output received"
    exit 1
fi

# Validate exported_count is 5
EXPORTED_COUNT=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('exported_count', 0))" 2>/dev/null || echo "0")
if [ "$EXPORTED_COUNT" -ne 5 ]; then
    echo "[dune_smoke] FAILED: expected exported_count=5, got $EXPORTED_COUNT"
    exit 1
fi

# Validate schema_version
SCHEMA_VERSION=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('schema_version', ''))" 2>/dev/null || echo "")
if [ "$SCHEMA_VERSION" != "wallet_profile.v1" ]; then
    echo "[dune_smoke] FAILED: expected schema_version=wallet_profile.v1, got $SCHEMA_VERSION"
    exit 1
fi

# Run with full output to check stderr
python3 -m integration.dune_source \
    --input-file integration/fixtures/discovery/dune_export_sample.csv \
    --dry-run \
    2>&1 | grep -q "DRY-RUN" || echo "[dune_smoke] WARNING: DRY-RUN message not found in stderr"

# Validate wallet_addr count (5 wallets in fixture)
python3 -m integration.dune_source \
    --input-file integration/fixtures/discovery/dune_export_sample.csv \
    --dry-run \
    --summary-json 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['exported_count'])" | grep -q "5" || exit 1

echo "[dune_smoke] validated 5 wallets against wallet_profile.v1 schema"
echo "[dune_smoke] OK"
