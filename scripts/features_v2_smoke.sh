#!/bin/bash
# scripts/features_v2_smoke.sh
# PR-C.3 Feature Engineering v2 Smoke Test

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[features_v2_smoke] Starting Feature Engineering v2 smoke test..." >&2

python3 << 'PYTHON_TEST'
import sys
import json
from collections import defaultdict

# Add root to path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from features.trade_features import (
    FEATURE_KEYS_V1, 
    FEATURE_KEYS_V2,
    build_features_v1, 
    build_features_v2
)
from integration.token_snapshot_store import TokenSnapshotStore, TokenSnapshot
from integration.trade_types import Trade
from integration.wallet_profile_store import WalletProfile

passed = 0
failed = 0

print("[features_v2_smoke] Testing FEATURE_KEYS_V2 contract...", file=sys.stderr)

# Test 1: Verify V2 includes all V1 keys
v1_keys_set = set(FEATURE_KEYS_V1)
v2_keys_set = set(FEATURE_KEYS_V2)
if v1_keys_set.issubset(v2_keys_set):
    print(f"  [features_v2] v2_includes_v1: PASS", file=sys.stderr)
    passed += 1
else:
    missing = v1_keys_set - v2_keys_set
    print(f"  [features_v2] v2_includes_v1: FAIL (missing: {missing})", file=sys.stderr)
    failed += 1

# Test 2: Verify V2 has the expected new keys
expected_v2_keys = {"f_token_vol_30s", "f_token_impulse_5m", "f_smart_money_share"}
if expected_v2_keys.issubset(v2_keys_set):
    print(f"  [features_v2] v2_new_keys: PASS", file=sys.stderr)
    passed += 1
else:
    missing = expected_v2_keys - v2_keys_set
    print(f"  [features_v2] v2_new_keys: FAIL (missing: {missing})", file=sys.stderr)
    failed += 1

print("[features_v2_smoke] Testing snapshot extra data capture...", file=sys.stderr)

# Test 3: Load snapshot store with v2 columns
try:
    snap_store = TokenSnapshotStore.from_csv(
        "/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/token_snapshot.v2.csv"
    )
    snap = snap_store.get("MINT_A")
    if snap is not None:
        print(f"  [features_v2] snapshot_load: PASS (mint={snap.mint})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] snapshot_load: FAIL (MINT_A not found)", file=sys.stderr)
        failed += 1
except Exception as e:
    print(f"  [features_v2] snapshot_load: FAIL ({e})", file=sys.stderr)
    failed += 1

# Test 4: Verify extra data contains v2 fields
if snap and snap.extra:
    vol_30s = snap.extra.get("volatility_30s")
    if vol_30s == 0.05:
        print(f"  [features_v2] extra_volatility_30s: PASS (value={vol_30s})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] extra_volatility_30s: FAIL (expected 0.05, got {vol_30s})", file=sys.stderr)
        failed += 1
    
    impulse_5m = snap.extra.get("price_change_5m_pct")
    if impulse_5m == 2.5:
        print(f"  [features_v2] extra_impulse_5m: PASS (value={impulse_5m})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] extra_impulse_5m: FAIL (expected 2.5, got {impulse_5m})", file=sys.stderr)
        failed += 1
    
    smart_share = snap.extra.get("smart_buy_ratio")
    if smart_share == 0.4:
        print(f"  [features_v2] extra_smart_money: PASS (value={smart_share})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] extra_smart_money: FAIL (expected 0.4, got {smart_share})", file=sys.stderr)
        failed += 1
else:
    print(f"  [features_v2] extra_fields: FAIL (no extra data)", file=sys.stderr)
    failed += 4

print("[features_v2_smoke] Testing build_features_v2...", file=sys.stderr)

# Test 5: Build features with v2 snapshot
if snap:
    trade = Trade(
        ts="2024-01-01T12:00:00Z",
        wallet="WALLET_A",
        mint="MINT_A",
        side="BUY",
        price=0.001,
        size_usd=100.0,
    )
    
    features = build_features_v2(trade, snap, None)
    
    # Check v1 features
    if "f_trade_size_usd" in features:
        print(f"  [features_v2] v1_in_output: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] v1_in_output: FAIL", file=sys.stderr)
        failed += 1
    
    # Check v2 features
    if abs(features.get("f_token_vol_30s", -1) - 0.05) < 0.01:
        print(f"  [features_v2] v2_vol_30s: PASS (value={features.get('f_token_vol_30s')})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] v2_vol_30s: FAIL (expected ~0.05, got {features.get('f_token_vol_30s')})", file=sys.stderr)
        failed += 1
    
    if abs(features.get("f_token_impulse_5m", -1) - 2.5) < 0.01:
        print(f"  [features_v2] v2_impulse_5m: PASS (value={features.get('f_token_impulse_5m')})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] v2_impulse_5m: FAIL (expected ~2.5, got {features.get('f_token_impulse_5m')})", file=sys.stderr)
        failed += 1
    
    if abs(features.get("f_smart_money_share", -1) - 0.4) < 0.01:
        print(f"  [features_v2] v2_smart_money: PASS (value={features.get('f_smart_money_share')})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [features_v2] v2_smart_money: FAIL (expected ~0.4, got {features.get('f_smart_money_share')})", file=sys.stderr)
        failed += 1
else:
    print(f"  [features_v2] build_v2: FAIL (no snapshot)", file=sys.stderr)
    failed += 5

print("[features_v2_smoke] Testing features_v2_expected.json contract...", file=sys.stderr)

# Test 6: Verify contract file
try:
    with open("/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/features_v2_expected.json", "r") as f:
        contract = json.load(f)
    
    contract_keys = set(contract.get("keys", []))
    if contract_keys == v2_keys_set:
        print(f"  [features_v2] contract_match: PASS", file=sys.stderr)
        passed += 1
    else:
        missing = v2_keys_set - contract_keys
        extra = contract_keys - v2_keys_set
        print(f"  [features_v2] contract_match: FAIL (missing: {missing}, extra: {extra})", file=sys.stderr)
        failed += 1
except Exception as e:
    print(f"  [features_v2] contract_match: FAIL ({e})", file=sys.stderr)
    failed += 1

# Summary
print(f"[features_v2_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)
if failed == 0:
    print("[features_v2_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
else:
    print("[features_v2_smoke] FAILED", file=sys.stderr)
    sys.exit(1)
PYTHON_TEST
