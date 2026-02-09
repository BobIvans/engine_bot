#!/bin/bash
set -e

# PR-M.1 Helius Webhook Parser Smoke Test
# Tests:
# 1. Valid SWAP payload -> normalized trade dict
# 2. Non-SWAP payload -> None
# 3. Output matches trade_schema.json requirements

cd "$(dirname "$0")/.."

echo "[overlay_lint] running helius smoke..." >&2

python3 -c "
import sys
sys.path.insert(0, '.')

import json
from ingestion.sources.helius import parse_helius_enhanced_tx

# Test 1: Valid SWAP payload
swap_payload = {
    'version': 0,
    'type': 'SWAP',
    'signature': '5w3m4e8v2x9c1z6k4j7h3g5f2d4s6a9p0o5i8u1y4t5r6e3w7q',
    'timestamp': 1707223405,
    'feePayer': '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU',
    'slot': 245678900,
    'tokenTransfers': [
        {
            'fromUserAccount': '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU',
            'toUserAccount': 'AnotherWallet111111111111111111111111111',
            'mint': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
            'tokenAmount': '100.50'
        },
        {
            'fromUserAccount': 'AnotherWallet111111111111111111111111111',
            'toUserAccount': '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU',
            'mint': '7V2sT3B7v2x9c1z6k4j7h3g5f2d4s6a9p0o5i8u1y4t5r',
            'tokenAmount': '2500000'
        }
    ],
    'nativeTransfers': []
}

result = parse_helius_enhanced_tx(swap_payload)
assert result is not None, 'Test 1 failed: expected non-None result for SWAP payload'
assert result['side'] == 'BUY', f'Test 1 failed: expected side=BUY, got {result[\"side\"]}'
assert result['mint'] == '7V2sT3B7v2x9c1z6k4j7h3g5f2d4s6a9p0o5i8u1y4t5r', f\"Test 1 failed: mint mismatch\"
assert result['wallet'] == '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU', f\"Test 1 failed: wallet mismatch\"
assert result['tx_hash'] == '5w3m4e8v2x9c1z6k4j7h3g5f2d4s6a9p0o5i8u1y4t5r6e3w7q', f\"Test 1 failed: tx_hash mismatch\"
assert result['source'] == 'helius_webhook', f\"Test 1 failed: source should be helius_webhook\"
print('Test 1: Valid SWAP payload -> normalized trade ... OK', file=sys.stderr)

# Test 2: Non-SWAP type -> None
unknown_payload = {
    'type': 'UNKNOWN',
    'signature': 'abc123',
    'timestamp': 1707223405,
    'feePayer': '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU',
    'tokenTransfers': []
}

result2 = parse_helius_enhanced_tx(unknown_payload)
assert result2 is None, f'Test 2 failed: expected None for UNKNOWN type, got {result2}'
print('Test 2: Non-SWAP type -> None ... OK', file=sys.stderr)

# Test 3: Empty tokenTransfers -> None
empty_payload = {
    'type': 'SWAP',
    'signature': 'abc123',
    'timestamp': 1707223405,
    'feePayer': '7Np41oWjZB3jCMKmMNJpZ2VT1Nb6mYdfG4UoFTJbYExU',
    'tokenTransfers': []
}

result3 = parse_helius_enhanced_tx(empty_payload)
assert result3 is None, f'Test 3 failed: expected None for empty tokenTransfers, got {result3}'
print('Test 3: Empty tokenTransfers -> None ... OK', file=sys.stderr)

# Test 4: SELL scenario (wallet sends token, receives native)
sell_payload = {
    'type': 'SWAP',
    'signature': 'sell_sig_abc123',
    'timestamp': 1707223406,
    'feePayer': 'WalletX111111111111111111111111111111',
    'slot': 245678901,
    'tokenTransfers': [
        {
            'fromUserAccount': 'WalletX111111111111111111111111111111',
            'toUserAccount': 'PoolAccount111111111111111111111111111',
            'mint': 'TokenMintABC12345678901234567890123456',
            'tokenAmount': '50000'
        },
        {
            'fromUserAccount': 'PoolAccount111111111111111111111111111',
            'toUserAccount': 'WalletX111111111111111111111111111111',
            'mint': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
            'tokenAmount': '25.0'
        }
    ],
    'nativeTransfers': []
}

result4 = parse_helius_enhanced_tx(sell_payload)
assert result4 is not None, 'Test 4 failed: expected non-None for SELL payload'
assert result4['side'] == 'SELL', f'Test 4 failed: expected side=SELL, got {result4[\"side\"]}'
print('Test 4: SELL scenario ... OK', file=sys.stderr)

# Test 5: Load from fixture file
with open('integration/fixtures/helius_enhanced_tx.json', 'r') as f:
    fixture = json.load(f)

result5 = parse_helius_enhanced_tx(fixture)
assert result5 is not None, 'Test 5 failed: fixture parsing returned None'
assert result5['side'] == 'BUY', f'Test 5 failed: expected BUY (wallet receives token), got {result5[\"side\"]}'
assert result5['mint'] == '7V2sT3B7v2x9c1z6k4j7h3g5f2d4s6a9p0o5i8u1y4t5r', f\"Test 5 failed: mint mismatch\"
print('Test 5: Fixture file parsing ... OK', file=sys.stderr)

print('[helius_smoke] OK', file=sys.stderr)
"
