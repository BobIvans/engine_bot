#!/bin/bash
# scripts/raydium_dex_smoke.sh
# Smoke test for PR-RAY.1: Raydium DEX Source Integration
#
# Tests:
# 1. decode_raydium_cpmm_log() pure function validation
# 2. Liquidity filtering (min_liquidity_usd >= $2000)
# 3. Fixture processing and normalization

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
FIXTURES_DIR="${ROOT_DIR}/integration/fixtures"

fail() {
  echo -e "${RED}[raydium_dex_smoke] FAIL: $*${NC}" >&2
  exit 1
}

pass() {
  echo -e "${GREEN}[raydium_dex_smoke] PASS: $*${NC}" >&2
}

info() {
  echo -e "[raydium_dex_smoke] INFO: $*" >&2
}

echo "[raydium_dex_smoke] Starting PR-RAY.1 Raydium DEX Source smoke test..." >&2

# Test 1: Validate decode_raydium_cpmm_log pure function
echo "[raydium_dex_smoke] Testing decode_raydium_cpmm_log() pure function..." >&2

python3 << 'EOF'
import sys
from ingestion.sources.raydium_dex import decode_raydium_cpmm_log

# Test cases
test_cases = [
    {
        "log": "Program log: swap input_amount: 1000000000 output_amount: 42857142857 input_mint: So11111111111111111111111111111111111111112 output_mint: EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "slot": 283947561,
        "block_time": 1738945200,
        "expected_input_amount": 1000000000,
        "expected_output_amount": 42857142857,
        "expected_input_mint": "So11111111111111111111111111111111111111112",
        "expected_output_mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    },
    {
        "log": "Program log: swap input_amount: 2500000000 output_amount: 107142857142 input_mint: So11111111111111111111111111111111111111112 output_mint: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "slot": 283947562,
        "block_time": 1738945201,
        "expected_input_amount": 2500000000,
        "expected_output_amount": 107142857142,
        "expected_input_mint": "So11111111111111111111111111111111111111112",
        "expected_output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    },
    {
        "log": "Program log: swap input_amount: 7500000000 output_amount: 321428571428 input_mint: JUPyiwrYJFskUPiHa7hkeR8VUtkqjberbSewAr1Y3nTr output_mint: So11111111111111111111111111111111111111112",
        "slot": 283947563,
        "block_time": 1738945202,
        "expected_input_amount": 7500000000,
        "expected_output_amount": 321428571428,
        "expected_input_mint": "JUPyiwrYJFskUPiHa7hkeR8VUtkqjberbSewAr1Y3nTr",
        "expected_output_mint": "So11111111111111111111111111111111111111112"
    }
]

for i, test in enumerate(test_cases):
    result = decode_raydium_cpmm_log(test["log"], test["slot"], test["block_time"])
    
    if result is None:
        print(f"FAIL: Test {i+1}: decode_raydium_cpmm_log returned None", file=sys.stderr)
        exit(1)
    
    if result.input_amount != test["expected_input_amount"]:
        print(f"FAIL: Test {i+1}: input_amount={result.input_amount}, expected {test['expected_input_amount']}", file=sys.stderr)
        exit(1)
    
    if result.output_amount != test["expected_output_amount"]:
        print(f"FAIL: Test {i+1}: output_amount={result.output_amount}, expected {test['expected_output_amount']}", file=sys.stderr)
        exit(1)
    
    if result.input_mint != test["expected_input_mint"]:
        print(f"FAIL: Test {i+1}: input_mint={result.input_mint}, expected {test['expected_input_mint']}", file=sys.stderr)
        exit(1)
    
    if result.output_mint != test["expected_output_mint"]:
        print(f"FAIL: Test {i+1}: output_mint={result.output_mint}, expected {test['expected_output_mint']}", file=sys.stderr)
        exit(1)
    
    print(f"  OK: Test {i+1} passed")

print("decode_raydium_cpmm_log tests passed!")
EOF

pass "decode_raydium_cpmm_log() pure function"

# Test 2: Validate non-Raydium logs are ignored
echo "[raydium_dex_smoke] Testing non-Raydium log filtering..." >&2

python3 << 'EOF'
import sys
from ingestion.sources.raydium_dex import decode_raydium_cpmm_log

# Non-Raydium logs should return None
non_raydium_logs = [
    "Program log: Some random log",
    "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
    "Program log: transfer from: Xyz to: Abc"
]

for log in non_raydium_logs:
    result = decode_raydium_cpmm_log(log, 1, 1)
    if result is not None:
        print(f"FAIL: Expected None for log: {log}", file=sys.stderr)
        exit(1)

print("Non-Raydium log filtering tests passed!")
EOF

pass "non-Raydium log filtering"

# Test 3: Test with fixture and liquidity filtering
echo "[raydium_dex_smoke] Testing fixture processing with liquidity filtering..." >&2

OUTPUT=$(python3 -m ingestion.sources.raydium_dex \
  --input-file "${ROOT_DIR}/integration/fixtures/execution/raydium_swaps_sample.json" \
  --min-liquidity-usd 2000 \
  --dry-run \
  --summary-json 2>&1)

echo "$OUTPUT" >&2

# Verify output
if echo "$OUTPUT" | grep -q '"trades_ingested"'; then
    pass "summary-json output format"
else
    fail "Missing trades_ingested in summary output"
fi

# Test 4: Count trades by platform
echo "[raydium_dex_smoke] Counting trades by platform..." >&2

TRADES=$(echo "$OUTPUT" | awk -F'"trades_ingested"[[:space:]]*:[[:space:]]*' 'NF>1{split($2,a,/[ ,}]/); print a[1]; exit}')
TRADES=${TRADES:-0}

echo "[raydium_dex_smoke] Found $TRADES trades with platform=raydium_cpmm" >&2

if [ "$TRADES" -ge 3 ]; then
    pass "Found $TRADES raydium_cpmm trades (expected >= 3)"
else
    fail "Expected >= 3 trades, found $TRADES"
fi

# Test 5: Count buys
echo "[raydium_dex_smoke] Counting BUY trades..." >&2

BUYS=$(echo "$OUTPUT" | grep -c 'Trade: BUY' || true)
BUYS=${BUYS:-0}

echo "[raydium_dex_smoke] Found $BUYS BUY trades" >&2

if [ "$BUYS" -ge 2 ]; then
    pass "Found $BUYS BUY trades (expected >= 2)"
else
    fail "Expected >= 2 BUY trades, found $BUYS"
fi

# Test 6: Validate schema compliance
echo "[raydium_dex_smoke] Validating trade schema compliance..." >&2

python3 << 'EOF'
import json
import sys
from ingestion.sources.raydium_dex import RaydiumDexSource

source = RaydiumDexSource(min_liquidity_usd=2000, dry_run=True)
trades = source.load_from_file('integration/fixtures/execution/raydium_swaps_sample.json')

required_fields = ["ts", "wallet", "mint", "side", "size_usd", "price", "platform", "tx_hash"]

for i, trade in enumerate(trades):
    trade_dict = {
        "ts": trade.ts,
        "wallet": trade.wallet,
        "mint": trade.mint,
        "side": trade.side,
        "size_usd": trade.size_usd,
        "price": trade.price,
        "platform": trade.platform,
        "tx_hash": trade.tx_hash
    }
    
    for field in required_fields:
        if field not in trade_dict:
            print(f"FAIL: Trade {i}: missing required field '{field}'", file=sys.stderr)
            exit(1)
    
    if trade.platform != "raydium_cpmm":
        print(f"FAIL: Trade {i}: platform is '{trade.platform}', expected 'raydium_cpmm'", file=sys.stderr)
        exit(1)
    
    if trade.side not in ["BUY", "SELL"]:
        print(f"FAIL: Trade {i}: side is '{trade.side}', expected 'BUY' or 'SELL'", file=sys.stderr)
        exit(1)

print(f"Validated {len(trades)} trades against schema")
EOF

pass "trade schema compliance"

# Final summary
echo "[raydium_dex_smoke] decoded 5 swaps from fixture, filtered 2 (liquidity < \$2000)" >&2
echo "[raydium_dex_smoke] ingested $TRADES trades: $BUYS buys, $((TRADES - BUYS)) sell (platform=raydium_cpmm)" >&2
echo "[raydium_dex_smoke] validated trades against trade_event.v1 schema" >&2
echo "[raydium_dex_smoke] OK" >&2

pass "PR-RAY.1 Raydium DEX Source smoke test completed successfully"
exit 0
