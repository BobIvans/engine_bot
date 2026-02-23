#!/bin/bash
# Smoke test for Performance Attribution Analysis
# Tests: PnL decomposition, aggregation, math verification

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/attribution"
OUTPUT_FILE="/tmp/pnl_attribution.json"

echo "[attribution_smoke] Starting performance attribution smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_FILE"

# Run attribution stage
echo "[attribution_smoke] Running attribution analysis..." >&2
python3 -m integration.attribution_stage \
    --trades "$FIXTURE_DIR/trades.jsonl" \
    --out "$OUTPUT_FILE" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "[attribution_smoke] FAIL: Output file not created" >&2
    exit 1
fi

# Test 1: Verify version format
echo "[attribution_smoke] Verifying output version..." >&2
VERSION=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['version'])")
if [ "$VERSION" != "pnl_attribution.v1" ]; then
    echo "[attribution_smoke] FAIL: Expected version 'pnl_attribution.v1', got '$VERSION'" >&2
    exit 1
fi

# Test 2: Verify first trade math (trade_001)
# signal=100, entry=101, exit=110, qty=1, fees=0.5
# Theoretical = (110-100)*1 = 10.0
# Execution Drag = (101-100)*1 = 1.0
# Net = 10 - 1 - 0.5 = 8.5
echo "[attribution_smoke] Verifying trade_001 math..." >&2
THEORETICAL=$(python3 -c "
import json
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from strategy.analytics.attribution import decompose_trade

trade = {'trade_id': 'trade_001', 'side': 'buy', 'qty': 1.0, 
         'price_signal': 100.0, 'price_entry': 101.0, 'price_exit': 110.0, 'fees_total': 0.5}
c = decompose_trade(trade)
print(f'{c.theoretical_pnl},{c.execution_drag},{c.fee_drag},{c.net_pnl}')
")

THEO=$(echo "$THEORETICAL" | cut -d',' -f1)
DRAG=$(echo "$THEORETICAL" | cut -d',' -f2)
FEES=$(echo "$THEORETICAL" | cut -d',' -f3)
NET=$(echo "$THEORETICAL" | cut -d',' -f4)

if [ "$THEO" != "10.0" ]; then
    echo "[attribution_smoke] FAIL: Expected theoretical_pnl=10.0, got $THEO" >&2
    exit 1
fi
echo "[attribution_smoke] Theoretical PnL: $THEO ✓" >&2

if [ "$DRAG" != "1.0" ]; then
    echo "[attribution_smoke] FAIL: Expected execution_drag=1.0, got $DRAG" >&2
    exit 1
fi
echo "[attribution_smoke] Execution Drag: $DRAG ✓" >&2

if [ "$FEES" != "0.5" ]; then
    echo "[attribution_smoke] FAIL: Expected fee_drag=0.5, got $FEES" >&2
    exit 1
fi
echo "[attribution_smoke] Fee Drag: $FEES ✓" >&2

if [ "$NET" != "8.5" ]; then
    echo "[attribution_smoke] FAIL: Expected net_pnl=8.5, got $NET" >&2
    exit 1
fi
echo "[attribution_smoke] Net PnL: $NET ✓" >&2

# Test 3: Verify Net = Theoretical - Execution Drag - Fees
echo "[attribution_smoke] Verifying PnL equation (Net = Theo - Drag - Fees)..." >&2
TOTAL_THEO=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_theoretical_pnl'])")
TOTAL_DRAG=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_execution_drag'])")
TOTAL_FEES=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_fee_drag'])")
TOTAL_NET=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_net_pnl'])")

EXPECTED_NET=$(python3 -c "print(round($TOTAL_THEO - $TOTAL_DRAG - $TOTAL_FEES, 6))")
if [ "$TOTAL_NET" != "$EXPECTED_NET" ]; then
    echo "[attribution_smoke] FAIL: Net equation mismatch. Net=$TOTAL_NET, Expected=$EXPECTED_NET" >&2
    exit 1
fi
echo "[attribution_smoke] PnL equation verified: $TOTAL_NET = $TOTAL_THEO - $TOTAL_DRAG - $TOTAL_FEES ✓" >&2

# Test 4: Verify aggregation has all trades
TRADE_COUNT=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_trades'])")
if [ "$TRADE_COUNT" != "3" ]; then
    echo "[attribution_smoke] FAIL: Expected 3 trades, got $TRADE_COUNT" >&2
    exit 1
fi
echo "[attribution_smoke] Trade count: $TRADE_COUNT ✓" >&2

# Cleanup
rm -f "$OUTPUT_FILE"

echo "[attribution_smoke] All attribution tests passed!" >&2
echo "[attribution_smoke] OK ✅"
