#!/bin/bash
# scripts/honeypot_smoke.sh
# PR-B.3 Honeypot Filter Integration - Deterministic Smoke Test

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[honeypot_smoke] Starting honeypot filter smoke test..." >&2

# Python test script
python3 << 'PYTHON_TEST'
import sys

# Add root to path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from strategy.honeypot_filter import check_security
from integration.token_snapshot_store import TokenSnapshot
from integration.reject_reasons import HONEYPOT_FLAG, HONEYPOT_FREEZE, HONEYPOT_MINT_AUTH

# Test counters
passed = 0
failed = 0

def test_case(name, expected_pass, expected_reason, snapshot, cfg):
    global passed, failed
    result_pass, result_reason = check_security(snapshot, cfg)
    
    if result_pass == expected_pass and result_reason == expected_reason:
        print(f"  [honeypot] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [honeypot] {name}: FAIL (got pass={result_pass}, reason={result_reason}, expected pass={expected_pass}, reason={expected_reason})", file=sys.stderr)
        failed += 1

print("[honeypot_smoke] Running pure logic tests...", file=sys.stderr)

# Configurations
cfg_enabled = {"token_profile": {"honeypot": {"enabled": True}}}
cfg_enabled_freeze = {"token_profile": {"honeypot": {"enabled": True, "reject_if_freeze_authority_present": True}}}
cfg_enabled_mint = {"token_profile": {"honeypot": {"enabled": True, "reject_if_mint_authority_present": True}}}
cfg_disabled = {"token_profile": {"honeypot": {"enabled": False}}}

# Test 1: Good token (no security issues) - should pass
good_security = {
    "is_honeypot": False,
    "freeze_authority": False,
    "mint_authority": False
}
good_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    extra={"security": good_security}
)
test_case(
    "good_token_passes",
    expected_pass=True,
    expected_reason=None,
    snapshot=good_snapshot,
    cfg=cfg_enabled
)

# Test 2: Honeypot flagged token - should fail with HONEYPOT_FLAG
honeypot_security = {
    "is_honeypot": True,
    "freeze_authority": False,
    "mint_authority": False
}
honeypot_snapshot = TokenSnapshot(
    mint="4STG2XSPty6j9u66oK7ptFfFkSbg7Y2K3i4Eq3S4c7qF",
    liquidity_usd=30000.0,
    extra={"security": honeypot_security}
)
test_case(
    "honeypot_token_rejected",
    expected_pass=False,
    expected_reason=HONEYPOT_FLAG,
    snapshot=honeypot_snapshot,
    cfg=cfg_enabled
)

# Test 3: Freeze authority token - should fail with HONEYPOT_FREEZE
freeze_security = {
    "is_honeypot": False,
    "freeze_authority": True,
    "mint_authority": False
}
freeze_snapshot = TokenSnapshot(
    mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPBzk",
    liquidity_usd=25000.0,
    extra={"security": freeze_security}
)
test_case(
    "freeze_authority_rejected",
    expected_pass=False,
    expected_reason=HONEYPOT_FREEZE,
    snapshot=freeze_snapshot,
    cfg=cfg_enabled_freeze
)

# Test 4: Mint authority token - should fail with HONEYPOT_MINT_AUTH
mint_security = {
    "is_honeypot": False,
    "freeze_authority": False,
    "mint_authority": True
}
mint_snapshot = TokenSnapshot(
    mint="7nYhPEPDysnfwadnJq3Tz4Q4j3G9J8XZJYJDDqyMDr3Y",
    liquidity_usd=40000.0,
    extra={"security": mint_security}
)
test_case(
    "mint_authority_rejected",
    expected_pass=False,
    expected_reason=HONEYPOT_MINT_AUTH,
    snapshot=mint_snapshot,
    cfg=cfg_enabled_mint
)

# Test 5: Honeypot disabled - all should pass
test_case(
    "honeypot_disabled_all_pass",
    expected_pass=True,
    expected_reason=None,
    snapshot=honeypot_snapshot,
    cfg=cfg_disabled
)

# Test 6: No snapshot - should fail with HONEYPOT_FLAG
test_case(
    "no_snapshot_fails",
    expected_pass=False,
    expected_reason=HONEYPOT_FLAG,
    snapshot=None,
    cfg=cfg_enabled
)

# Test 7: No security data in snapshot - should fail with HONEYPOT_FLAG
no_security_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    extra={}
)
test_case(
    "no_security_data_fails",
    expected_pass=False,
    expected_reason=HONEYPOT_FLAG,
    snapshot=no_security_snapshot,
    cfg=cfg_enabled
)

# Test 8: Signal engine integration test
print("[honeypot_smoke] Running signal engine integration test...", file=sys.stderr)
from strategy.signal_engine import decide_entry
from integration.trade_types import Trade

# Create a trade
trade = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="test_wallet",
    mint="So11111111111111111111111111111111111111112",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    tx_hash="0x123"
)

# Test that good token passes through signal engine
decision = decide_entry(
    trade=trade,
    snapshot=good_snapshot,
    wallet_profile=None,
    cfg=cfg_enabled
)

if decision.should_enter and decision.reason == "entry_ok":
    print("  [honeypot] signal_engine_integration: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [honeypot] signal_engine_integration: FAIL (should_enter={decision.should_enter}, reason={decision.reason})", file=sys.stderr)
    failed += 1

# Test that honeypot token is rejected by signal engine
decision = decide_entry(
    trade=trade,
    snapshot=honeypot_snapshot,
    wallet_profile=None,
    cfg=cfg_enabled
)

if not decision.should_enter and decision.reason == HONEYPOT_FLAG:
    print("  [honeypot] signal_engine_honeypot_reject: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [honeypot] signal_engine_honeypot_reject: FAIL (should_enter={decision.should_enter}, reason={decision.reason})", file=sys.stderr)
    failed += 1

# Summary
print(f"\n[honeypot_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[honeypot_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[honeypot_smoke] Smoke test completed." >&2
