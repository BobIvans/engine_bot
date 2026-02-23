#!/bin/bash
set -e

# Smoke test for Smart Money Tracker feature
# Verifies sliding window counting of Tier 0/1 wallets

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${YELLOW}[smart_money_smoke] INFO: $1${NC}" >&2
}

log_pass() {
    echo -e "${GREEN}[smart_money_smoke] INFO: $1${NC}" >&2
}

log_fail() {
    echo -e "${RED}[smart_money_smoke] ERROR: $1${NC}" >&2
}

cleanup() {
    rm -rf "$TMPDIR"
    log_info "Cleaned up temporary files"
}
trap cleanup EXIT

# Create temporary directory
TMPDIR=$(mktemp -d)
export TMPDIR
log_info "Using temp dir: $TMPDIR"

# Change to project root
cd "$PROJECT_ROOT"

# Run Python smoke test
log_info "Running Smart Money Tracker smoke test..."

python3 -c "
import sys
import json
sys.path.insert(0, '$PROJECT_ROOT')

from strategy.features.smart_money import SmartMoneyTracker, TradeEvent, create_trade_from_dict

# Initialize tracker with 300s window
tracker = SmartMoneyTracker(window_sec=300)
state = []

# Test case 1: T=0s, Wallet=A (Tier 2) -> Count 0
trade1 = TradeEvent(
    wallet='WalletA',
    wallet_tier='T2',
    ts=1700000000,
    mint='SOL123',
    tx_hash='tx1',
    side='BUY',
    price=100.0,
    size_usd=1000.0,
)
state, count = tracker.update(state, trade1, now_ts=1700000000)
assert count == 0, f'Expected 1, got {count}'
print('Test 1 PASSED: T2 wallet counted as 0', file=sys.stderr)

# Test case 2: T=10s, Wallet=B (Tier 1) -> Count 1
trade2 = TradeEvent(
    wallet='WalletB',
    wallet_tier='T1',
    ts=1700000010,
    mint='SOL123',
    tx_hash='tx2',
    side='BUY',
    price=101.0,
    size_usd=2000.0,
)
state, count = tracker.update(state, trade2, now_ts=1700000010)
assert count == 1, f'Expected 1, got {count}'
print('Test 2 PASSED: T1 wallet counted as 1', file=sys.stderr)

# Test case 3: T=20s, Wallet=C (Tier 0) -> Count 2
trade3 = TradeEvent(
    wallet='WalletC',
    wallet_tier='T0',
    ts=1700000020,
    mint='SOL123',
    tx_hash='tx3',
    side='BUY',
    price=102.0,
    size_usd=3000.0,
)
state, count = tracker.update(state, trade3, now_ts=1700000020)
assert count == 2, f'Expected 2, got {count}'
print('Test 3 PASSED: T0 wallet counted, total 2 unique smart wallets', file=sys.stderr)

# Test case 4: T=30s, Wallet=B (Tier 1) -> Count 2 (duplicate wallet ignored)
trade4 = TradeEvent(
    wallet='WalletB',
    wallet_tier='T1',
    ts=1700000030,
    mint='SOL123',
    tx_hash='tx4',
    side='BUY',
    price=103.0,
    size_usd=1500.0,
)
state, count = tracker.update(state, trade4, now_ts=1700000030)
assert count == 2, f'Expected 2 (duplicate wallet), got {count}'
print('Test 4 PASSED: Duplicate smart wallet not double-counted', file=sys.stderr)

# Test case 5: T=350s (Window expired for T=0s, T=10s, T=20s, T=30s)
# New time: 1700000350, window is 300s, so cutoff is 1700000050
# Trade1 (T0, T2) expired, Trade2 (T10, T1) expired, Trade3 (T20, T0) expired, Trade4 (T30, T1) expired
# New trade at T=350s with WalletD (T1)
trade5 = TradeEvent(
    wallet='WalletD',
    wallet_tier='T1',
    ts=1700000350,
    mint='SOL123',
    tx_hash='tx5',
    side='BUY',
    price=105.0,
    size_usd=2500.0,
)
state, count = tracker.update(state, trade5, now_ts=1700000350)
assert count == 1, f'Expected 1 (only WalletD in window), got {count}'
print('Test 5 PASSED: Old entries expired, only new T1 wallet counted', file=sys.stderr)

# Test case 6: Feature builder integration
print('Test 6: Feature builder integration...', file=sys.stderr)
from strategy.features.feature_builder import compute_features_batch, reset_smart_money_tracker

reset_smart_money_tracker()

trades = [
    {'wallet': 'A', 'wallet_tier': 'T2', 'ts': 1000, 'mint': 'SOL', 'tx_hash': 'a1', 'side': 'BUY', 'price': 100, 'size_usd': 1000},
    {'wallet': 'B', 'wallet_tier': 'T1', 'ts': 1010, 'mint': 'SOL', 'tx_hash': 'b1', 'side': 'BUY', 'price': 101, 'size_usd': 2000},
    {'wallet': 'C', 'wallet_tier': 'T0', 'ts': 1020, 'mint': 'SOL', 'tx_hash': 'c1', 'side': 'BUY', 'price': 102, 'size_usd': 3000},
]

results, final_state = compute_features_batch(trades, smart_money_window_sec=300)
assert results[0]['smart_money_entry_count_5m'] == 0, f'Expected 1, got {results[0]}'
assert results[1]['smart_money_entry_count_5m'] == 1, f'Expected 1, got {results[1]}'
assert results[2]['smart_money_entry_count_5m'] == 2, f'Expected 2, got {results[2]}'
print('Test 6 PASSED: Feature builder computes smart_money_entry_count_5m correctly', file=sys.stderr)

# Test case 7: Case-insensitive tier matching
print('Test 7: Case-insensitive tier matching...', file=sys.stderr)
reset_smart_money_tracker()

trades_lower = [
    {'wallet': 'X', 'wallet_tier': 'tier0', 'ts': 1000, 'mint': 'SOL', 'tx_hash': 'x1', 'side': 'BUY', 'price': 100, 'size_usd': 1000},
    {'wallet': 'Y', 'wallet_tier': 'tier1', 'ts': 1010, 'mint': 'SOL', 'tx_hash': 'y1', 'side': 'BUY', 'price': 101, 'size_usd': 2000},
]
results_lower, _ = compute_features_batch(trades_lower, smart_money_window_sec=300)
assert results_lower[0]['smart_money_entry_count_5m'] == 1, f'Expected 1, got {results_lower[0]}'
assert results_lower[1]['smart_money_entry_count_5m'] == 2, f'Expected 2, got {results_lower[1]}'
print('Test 7 PASSED: Case-insensitive tier matching works', file=sys.stderr)

print('', file=sys.stderr)
print('[smart_money_smoke] OK', file=sys.stderr)
"

echo -e "${GREEN}[smart_money_smoke] OK ✅${NC}"
