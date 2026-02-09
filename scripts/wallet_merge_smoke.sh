#!/bin/bash
# scripts/wallet_merge_smoke.sh
# Smoke test for Multi-Source Wallet Dedup & Merge

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[wallet_merge_smoke] Starting wallet merge smoke test..." >&2

# Navigate to project root
cd "$ROOT_DIR"

# Test 1: Verify fixture files exist and are valid
echo "[wallet_merge_smoke] Validating fixture files..." >&2
if [[ -f "integration/fixtures/discovery/dune_sample_merge.csv" ]] && \
   [[ -f "integration/fixtures/discovery/flipside_sample_merge.csv" ]] && \
   [[ -f "integration/fixtures/discovery/kolscan_sample_merge.json" ]]; then
    echo "[wallet_merge_smoke] All fixture files exist ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: Missing fixture files${NC}" >&2
    exit 1
fi

# Test 2: Run merge on fixture files via CLI
echo "[wallet_merge_smoke] Running merge on fixture files..." >&2

OUTPUT=$(python3 -m integration.wallet_merge \
  --input-dune integration/fixtures/discovery/dune_sample_merge.csv \
  --input-flipside integration/fixtures/discovery/flipside_sample_merge.csv \
  --input-kolscan integration/fixtures/discovery/kolscan_sample_merge.json \
  --dry-run \
  --summary-json 2>&1)

# Check unique_wallets count (should be 4: W1, W2, W3, W4)
echo "[wallet_merge_smoke] Checking unique_wallets..." >&2
UNIQUE=$(echo "$OUTPUT" | grep -o '"unique_wallets": [0-9]*' | cut -d' ' -f2 || echo "")

if [[ "$UNIQUE" == "4" ]]; then
    echo "[wallet_merge_smoke] unique_wallets = 4 ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: expected unique_wallets=4, got '$UNIQUE'${NC}" >&2
    echo "Output: $OUTPUT" >&2
    exit 1
fi

# Check sources_merged (should be 3)
echo "[wallet_merge_smoke] Checking sources_merged..." >&2
SOURCES=$(echo "$OUTPUT" | grep -o '"sources_merged": [0-9]*' | cut -d' ' -f2 || echo "")

if [[ "$SOURCES" == "3" ]]; then
    echo "[wallet_merge_smoke] sources_merged = 3 ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: expected sources_merged=3, got '$SOURCES'${NC}" >&2
    exit 1
fi

# Test 3: Verify schema_version
echo "[wallet_merge_smoke] Checking schema_version..." >&2
if echo "$OUTPUT" | grep -q '"schema_version": "wallet_profile.v1"'; then
    echo "[wallet_merge_smoke] schema_version = wallet_profile.v1 ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: schema_version not found${NC}" >&2
    exit 1
fi

# Test 4: Verify --skip-merge flag exists in wallet_discovery.py
echo "[wallet_merge_smoke] Verifying --skip-merge flag..." >&2
if python3 -m integration.wallet_discovery --help 2>&1 | grep -q "\-\-skip-merge"; then
    echo "[wallet_merge_smoke] --skip-merge flag is available ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: --skip-merge flag not found in wallet_discovery.py${NC}" >&2
    exit 1
fi

# Test 5: Verify merge logic via Python (conflict resolution test)
echo "[wallet_merge_smoke] Testing merge logic (conflict resolution)..." >&2

PYTHON_OUTPUT=$(python3 -c "
from integration.wallet_merge import load_profiles, merge_wallet_profiles

dune = load_profiles('dune', 'integration/fixtures/discovery/dune_sample_merge.csv')
flipside = load_profiles('flipside', 'integration/fixtures/discovery/flipside_sample_merge.csv')
kolscan = load_profiles('kolscan', 'integration/fixtures/discovery/kolscan_sample_merge.json')

merged = merge_wallet_profiles([('dune', dune), ('flipside', flipside), ('kolscan', kolscan)])

# Check W3 has roi_30d from Flipside (trades_30d=215 > 45)
for p in merged:
    if p.wallet_addr == 'W3':
        assert p.roi_30d == 0.49, f'W3 roi_30d should be 0.49, got {p.roi_30d}'
        print('W3 conflict resolution: OK')

# Check W1 has kolscan_flags
for p in merged:
    if p.wallet_addr == 'W1':
        assert p.kolscan_flags == ['memecoin_specialist', 'verified'], f'W1 flags wrong: {p.kolscan_flags}'
        print('W1 kolscan enrichment: OK')

print('merge_logic: OK')
" 2>&1)

if echo "$PYTHON_OUTPUT" | grep -q "merge_logic: OK"; then
    echo "[wallet_merge_smoke] Merge logic tests pass ✅" >&2
else
    echo -e "${RED}[wallet_merge_smoke] FAIL: Merge logic test failed${NC}" >&2
    echo "$PYTHON_OUTPUT" >&2
    exit 1
fi

# Final success message
echo "[wallet_merge_smoke] merged 3 sources → 4 unique wallets" >&2
echo -e "${GREEN}[wallet_merge_smoke] OK${NC}" >&2

exit 0
