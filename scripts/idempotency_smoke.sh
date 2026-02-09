#!/bin/bash
# scripts/idempotency_smoke.sh
# PR-G.2 Idempotency Layer & Reorg Guard - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"

echo "[idempotency_smoke] Starting idempotency and reorg guard smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import json
import os
import tempfile
import time
import unittest.mock as mock

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [idempotency] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [idempotency] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[idempotency_smoke] Testing IdempotencyManager...", file=sys.stderr)

from execution.idempotency import IdempotencyManager

# Create a temporary state file
with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
    state_file = f.name

try:
    # Test 1: Create manager
    manager = IdempotencyManager(state_file=state_file, ttl_sec=60)
    test_case("manager_created", manager is not None)
    test_case("state_file_exists", os.path.exists(state_file))

    # Test 2: Generate deterministic key
    signal = {
        "wallet": "7nYAh1wXYZ4sL5YmR8XZ1yZW2Xg6iZw4z3Xp3KZwPNp1",
        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "side": "buy",
    }
    key1 = manager.generate_key(signal=signal)
    test_case("key_generated", len(key1) == 64)  # SHA256 hex is 64 chars
    test_case("key_is_hex", all(c in '0123456789abcdef' for c in key1))

    # Same signal should generate same key
    key2 = manager.generate_key(signal=signal)
    test_case("key_deterministic", key1 == key2)

    # Different signal should generate different key
    signal["side"] = "sell"
    key3 = manager.generate_key(signal=signal)
    test_case("key_differs_for_different_signal", key1 != key3)

    # Test 3: Acquire lock
    test_case("lock_acquired_first", manager.acquire_lock(key=key1) == True)

    # Test 4: Duplicate lock should fail
    test_case("duplicate_lock_rejected", manager.acquire_lock(key=key1) == False)

    # Test 5: Different key should succeed
    test_case("different_lock_acquired", manager.acquire_lock(key=key3) == True)

    # Test 6: Check lock status
    test_case("check_existing_lock", manager.check(key=key1) == True)
    test_case("check_missing_lock", manager.check(key="nonexistent") == False)

    # Test 7: Release lock
    test_case("lock_released", manager.release_lock(key=key1) == True)
    test_case("lock_gone_after_release", manager.check(key=key1) == False)

    # Test 8: Prune expired locks (wait briefly)
    manager2 = IdempotencyManager(state_file=state_file, ttl_sec=1)
    test_key = manager2.generate_key(signal={"wallet": "test", "mint": "mint", "side": "sell"})
    manager2.acquire_lock(key=test_key)
    time.sleep(1.1)  # Wait for TTL to expire
    removed = manager2.prune()
    test_case("prune_removes_expired", removed >= 1)

    print("[idempotency_smoke] Testing ReorgGuard...", file=sys.stderr)

    from execution.reorg_guard import ReorgGuard

    # Test 9: Verify reject constants exist
    from integration.reject_reasons import DUPLICATE_EXECUTION, TX_DROPPED, TX_REORGED
    test_case("reject_duplicate_exists", DUPLICATE_EXECUTION == "duplicate_execution")
    test_case("reject_dropped_exists", TX_DROPPED == "tx_dropped")
    test_case("reject_reorged_exists", TX_REORGED == "tx_reorged")

    # Test 10: ReorgGuard FINALIZED response
    RPC_FINALIZED_RESPONSE = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "value": [
                {
                    "signature": "test_signature_finalized",
                    "slot": 100,
                    "confirmations": None,
                    "status": {"Ok": None},
                    "err": None,
                }
            ]
        },
    }

    # Mock the RPC call directly
    with mock.patch.object(ReorgGuard, '_rpc_request') as mock_rpc:
        # When getSignatureStatuses is called, return finalized status
        # When getBlockHeight is called, return 300
        def side_effect(method, params=None):
            if method == "getSignatureStatuses":
                return RPC_FINALIZED_RESPONSE
            elif method == "getBlockHeight":
                return {"jsonrpc": "2.0", "id": 1, "result": 300}
            return {}

        mock_rpc.side_effect = side_effect

        guard = ReorgGuard()
        status = guard.check_tx_status(
            tx_hash="test_signature_finalized",
            last_valid_block_height=200,
        )
        test_case("reorg_finalized", status == "FINALIZED")

    # Test 11: ReorgGuard DROPPED response
    RPC_DROPPED_RESPONSE = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "value": [None]
        },
    }

    with mock.patch.object(ReorgGuard, '_rpc_request') as mock_rpc:
        def side_effect(method, params=None):
            if method == "getSignatureStatuses":
                return RPC_DROPPED_RESPONSE
            elif method == "getBlockHeight":
                return {"jsonrpc": "2.0", "id": 1, "result": 300}
            return {}

        mock_rpc.side_effect = side_effect

        guard = ReorgGuard()
        status = guard.check_tx_status(
            tx_hash="test_signature_dropped",
            last_valid_block_height=200,
        )
        test_case("reorg_dropped", status == "DROPPED")

    # Test 12: ReorgGuard CONFIRMED response (has confirmations, slot close to current)
    # This tests the CONFIRMED state (confirmed but not yet finalized)
    RPC_CONFIRMED_RESPONSE = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "value": [
                {
                    "signature": "test_signature_pending",
                    "slot": 295,
                    "confirmations": 10,
                    "status": {"Ok": None},
                    "err": None,
                }
            ]
        },
    }

    with mock.patch.object(ReorgGuard, '_rpc_request') as mock_rpc:
        def side_effect(method, params=None):
            if method == "getSignatureStatuses":
                return RPC_CONFIRMED_RESPONSE
            elif method == "getBlockHeight":
                return {"jsonrpc": "2.0", "id": 1, "result": 300}
            return {}

        mock_rpc.side_effect = side_effect

        guard = ReorgGuard()
        status = guard.check_tx_status(
            tx_hash="test_signature_pending",
            last_valid_block_height=200,
        )
        test_case("reorg_confirmed", status == "CONFIRMED")

finally:
    # Cleanup temp file
    if os.path.exists(state_file):
        os.unlink(state_file)

# Summary
print(f"\n[idempotency_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[idempotency_smoke] OK", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[idempotency_smoke] Smoke test completed." >&2
