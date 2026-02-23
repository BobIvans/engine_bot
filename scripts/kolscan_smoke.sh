#!/bin/bash
# scripts/kolscan_smoke.sh
# Smoke test for Kolscan API adapter

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[kolscan_smoke] Starting Kolscan smoke test..." >&2

# Navigate to project root
cd "$ROOT_DIR"

# Run kolscan adapter on fixture in dry-run mode with summary-json
echo "[kolscan_smoke] Running kolscan adapter on fixture..." >&2

OUTPUT=$(python3 -m ingestion.sources.kolscan \
  --input-file integration/fixtures/discovery/kolscan_sample.json \
  --dry-run \
  --summary-json 2>&1)

# Check stdout for enriched_count
echo "[kolscan_smoke] Checking output..." >&2

ENRICHED_COUNT=$(echo "$OUTPUT" | grep -o '"enriched_count": [0-9]*' | cut -d' ' -f2 || echo "")

if [[ "$ENRICHED_COUNT" == "3" ]]; then
    echo "[kolscan_smoke] enriched_count = 3" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: expected enriched_count=3, got '$ENRICHED_COUNT'${NC}" >&2
    echo "Output: $OUTPUT" >&2
    exit 1
fi

# Check for kolscan_available in output (can be true or false in fixture mode)
if echo "$OUTPUT" | grep -q '"kolscan_available":'; then
    echo "[kolscan_smoke] kolscan_available present" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: kolscan_available not found${NC}" >&2
    exit 1
fi

# Check for kolscan_rank in actual wallet data (not just summary)
if echo "$OUTPUT" | grep -q '"kolscan_rank"'; then
    echo "[kolscan_smoke] kolscan_rank present in output" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: kolscan_rank not found in output${NC}" >&2
    exit 1
fi

# Count wallet_addr occurrences (should be 3)
WALLET_COUNT=$(echo "$OUTPUT" | grep -c '"wallet_addr"' || echo "0")
if [[ "$WALLET_COUNT" == "3" ]]; then
    echo "[kolscan_smoke] Found 3 wallet records" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: expected 3 wallets, found $WALLET_COUNT${NC}" >&2
    exit 1
fi

# Test schema version
if echo "$OUTPUT" | grep -q '"schema_version": "wallet_profile.v1"'; then
    echo "[kolscan_smoke] schema_version = wallet_profile.v1" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: schema_version not found or incorrect${NC}" >&2
    exit 1
fi

# Verify kolscan_flags are present
if echo "$OUTPUT" | grep -q '"kolscan_flags"'; then
    echo "[kolscan_smoke] kolscan_flags present in output" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: kolscan_flags not found in output${NC}" >&2
    exit 1
fi

# Test that --allow-kolscan flag exists and is recognized
echo "[kolscan_smoke] Verifying --allow-kolscan flag..." >&2
if python3 -m ingestion.sources.kolscan --help 2>&1 | grep -q "\-\-allow-kolscan"; then
    echo "[kolscan_smoke] --allow-kolscan flag is available" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: --allow-kolscan flag not found${NC}" >&2
    exit 1
fi

# Validate fixture file exists and is valid JSON
echo "[kolscan_smoke] Validating fixture file..." >&2
if python3 -c "import json; json.load(open('integration/fixtures/discovery/kolscan_sample.json'))" 2>/dev/null; then
    echo "[kolscan_smoke] Fixture file is valid JSON" >&2
else
    echo -e "${RED}[kolscan_smoke] FAIL: Fixture file is not valid JSON${NC}" >&2
    exit 1
fi

# Final success message
echo "[kolscan_smoke] enriched 3 wallets with kolscan metadata" >&2
echo -e "${GREEN}[kolscan_smoke] OK${NC}" >&2

exit 0
