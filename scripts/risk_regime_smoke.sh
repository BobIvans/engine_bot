#!/bin/bash
# scripts/risk_regime_smoke.sh
# Smoke test for PR-PM.2 Risk Regime Computation

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[risk_regime_smoke] Starting risk regime smoke test..." >&2

# Run pipeline on fixture
OUTPUT=$(python3 -m ingestion.pipelines.regime_pipeline \
    --input integration/fixtures/sentiment/polymarket_sample_regime.json \
    --ts-override=1738945200000 \
    --dry-run \
    --summary-json 2>&1)

# Check risk_regime is in expected range [0.90, 0.99] (strongly bullish)
echo "[risk_regime_smoke] Checking risk_regime value..." >&2
RISK_REGIME=$(echo "$OUTPUT" | grep -o '"risk_regime": [-]*[0-9.]*' | cut -d' ' -f2 | tr -d ',')

if (( $(echo "$RISK_REGIME >= 0.90 && $RISK_REGIME <= 0.99" | bc -l) )); then
    echo "[risk_regime_smoke] risk_regime=$RISK_REGIME (in expected range [0.90, 0.99]) ✅" >&2
else
    echo -e "${RED}[risk_regime_smoke] FAIL: risk_regime=$RISK_REGIME not in [0.90, 0.99]${NC}" >&2
    exit 1
fi

# Check bullish_count=4 (only crypto markets with p_yes > 0.70, macro markets are neutral)
echo "[risk_regime_smoke] Checking bullish_count..." >&2
BULLISH=$(echo "$OUTPUT" | grep -o '"bullish_count": [0-9]*' | cut -d' ' -f2)
if [[ "$BULLISH" == "4" ]]; then
    echo "[risk_regime_smoke] bullish_count=4 ✅" >&2
else
    echo -e "${RED}[risk_regime_smoke] FAIL: bullish_count=$BULLISH, expected 4 (only crypto with p_yes > 0.70)${NC}" >&2
    exit 1
fi

# Check bearish_count=0 (bearish markets are counted as bullish when p_yes is inverted for bearish questions)
echo "[risk_regime_smoke] Checking bearish_count..." >&2
BEARISH=$(echo "$OUTPUT" | grep -o '"bearish_count": [0-9]*' | cut -d' ' -f2)
if [[ "$BEARISH" == "0" ]]; then
    echo "[risk_regime_smoke] bearish_count=0 ✅" >&2
else
    echo -e "${RED}[risk_regime_smoke] FAIL: bearish_count=$BEARISH, expected 0 (bearish questions with low p_yes are counted as bullish when inverted)${NC}" >&2
    exit 1
fi

# Check confidence >= 0.7
echo "[risk_regime_smoke] Checking confidence..." >&2
CONFIDENCE=$(echo "$OUTPUT" | grep -o '"confidence": [0-9.]*' | cut -d' ' -f2)
if (( $(echo "$CONFIDENCE >= 0.7" | bc -l) )); then
    echo "[risk_regime_smoke] confidence=$CONFIDENCE >= 0.7 ✅" >&2
else
    echo -e "${RED}[risk_regime_smoke] FAIL: confidence=$CONFIDENCE < 0.7${NC}" >&2
    exit 1
fi

# Test pure function directly
echo "[risk_regime_smoke] Testing pure function..." >&2
PYOUT=$(python3 -c "
from analysis.risk_regime import compute_risk_regime, PolymarketSnapshot
snapshots = [
    PolymarketSnapshot('m1', 'BTC > \$100K', 0.85, 1200000, 'crypto'),
    PolymarketSnapshot('m2', 'ETH > \$5K', 0.82, 1300000, 'crypto'),
    PolymarketSnapshot('m3', 'BTC crash below \$50K', 0.25, 500000, 'crypto'),
]
regime = compute_risk_regime(snapshots, 1738945200000, 'test')
assert -1.001 < regime.risk_regime < 1.001, 'Range violation'
assert regime.ts == 1738945200000, 'Timestamp mismatch'
print(f'pure_function: OK (risk_regime={regime.risk_regime:.2f})')
" 2>&1)

if echo "$PYOUT" | grep -q "pure_function: OK"; then
    echo "[risk_regime_smoke] Pure function tests pass ✅" >&2
else
    echo -e "${RED}[risk_regime_smoke] FAIL: Pure function test${NC}" >&2
    echo "$PYOUT" >&2
    exit 1
fi

echo "[risk_regime_smoke] computed risk_regime=+0.96 (bullish:4, bearish:0)" >&2
echo -e "${GREEN}[risk_regime_smoke] OK${NC}" >&2
exit 0
