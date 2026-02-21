#!/bin/bash
# scripts/polymarket_smoke.sh

set -e

echo "[overlay_lint] running polymarket smoke..."

cd "$(dirname "$0")/.."

# Test that the normalization works on fixture
python3 << 'PYTHON_TEST'
import sys
sys.path.insert(0, '.')

from strategy.sentiment import normalize_polymarket_market
import json

SCHEMA_VERSION = "polymarket_snapshot.v1"
FIXED_TS = 1738945200000  # Fixed timestamp for deterministic test

# Load fixture
with open('integration/fixtures/sentiment/polymarket_sample.json') as f:
    markets = json.load(f)

# Normalize all markets
normalized = []
for raw in markets:
    snapshot = normalize_polymarket_market(raw, FIXED_TS)
    normalized.append(snapshot)
    print(f"Normalized: {snapshot.market_id[:32]}... p_yes={snapshot.p_yes:.2f} tags={snapshot.category_tags}")

# Validate count
assert len(normalized) == 5, f"Expected 5 snapshots, got {len(normalized)}"

# Validate crypto tags
crypto_count = sum(1 for s in normalized if 'crypto' in s.category_tags)
assert crypto_count >= 3, f"Expected >=3 crypto markets, got {crypto_count}"

# Validate specific p_yes value
p_78_count = sum(1 for s in normalized if abs(s.p_yes - 0.78) < 0.01)
assert p_78_count == 1, f"Expected 1 market with p_yes=0.78, got {p_78_count}"

print(f"[polymarket_smoke] validated {len(normalized)} markets against {SCHEMA_VERSION} schema")
PYTHON_TEST

# Run the CLI on fixture
echo "[polymarket_smoke] Testing CLI interface..."

OUTPUT=$(python3 -c "
from ingestion.sources.polymarket import main
import sys
sys.argv = ['polymarket', '--input-file', 'integration/fixtures/sentiment/polymarket_sample.json', '--fixed-ts', '1738945200000', '--summary-json']
main()
" 2>/dev/null)

echo "CLI Output: $OUTPUT"

# Validate JSON output
SNAPSHOT_COUNT=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['snapshot_count'])")
TS_VALUE=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['ts'])")
SCHEMA_VER=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['schema_version'])")

if [ "$SNAPSHOT_COUNT" != "5" ]; then
    echo "[polymarket_smoke] FAILED: Expected snapshot_count=5, got $SNAPSHOT_COUNT"
    exit 1
fi

if [ "$TS_VALUE" != "1738945200000" ]; then
    echo "[polymarket_smoke] FAILED: Expected ts=1738945200000, got $TS_VALUE"
    exit 1
fi

if [ "$SCHEMA_VER" != "polymarket_snapshot.v1" ]; then
    echo "[polymarket_smoke] FAILED: Expected schema_version=polymarket_snapshot.v1, got $SCHEMA_VER"
    exit 1
fi

echo "[polymarket_smoke] OK"
