#!/usr/bin/env bash
set -eo pipefail
# Smoke test for PR-G.4 Jito Bundle Strategy Executor.
# Tests the JitoClient abstraction and bundle construction.
# NOTE: This test runs in MOCK mode - no real network calls.

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from script
project_root="$(dirname "$SCRIPT_DIR")"

echo "project_root: $project_root" >&2

# Add project to PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}:$project_root"

# Import the Jito module
python3 << 'PYTHON_IMPORT'
import sys
import asyncio

def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

def test_jito_reasons_known():
    """Test 1: Verify Jito reject reasons are known."""
    log("[jito_bundle_smoke] Testing Jito reject reasons are known...")
    
    from integration.reject_reasons import (
        JITOBUNDLE_REJECTED,
        JITOBUNDLE_TIMEOUT,
        JITOBUNDLE_TIP_TOO_LOW,
        JITOBUNDLE_NETWORK_ERROR,
        assert_reason_known,
    )
    
    reasons = [
        JITOBUNDLE_REJECTED,
        JITOBUNDLE_TIMEOUT,
        JITOBUNDLE_TIP_TOO_LOW,
        JITOBUNDLE_NETWORK_ERROR,
    ]
    
    for r in reasons:
        assert_reason_known(r)
        log(f"[jito_bundle_smoke] {r} is known reason")
    
    log("[jito_bundle_smoke] Test 1 PASSED: All Jito reject reasons known")
    return True

def test_jito_structs():
    """Test 2: Test Jito data structures."""
    log("[jito_bundle_smoke] Testing Jito data structures...")
    
    from execution.jito_structs import (
        JitoBundleRequest,
        JitoBundleResponse,
        JitoTipAccount,
        JitoConfig,
    )
    from execution.jito_structs import Pubkey
    
    # Test JitoConfig
    config = JitoConfig(
        enabled=True,
        endpoint="https://test.block-engine.jito.wtf",
        tip_multiplier=1.5,
        min_tip_lamports=1000,
        max_tip_lamports=100000,
    )
    
    assert config.enabled == True
    assert config.tip_multiplier == 1.5
    assert config.min_tip_lamports == 1000
    
    # Test JitoBundleResponse
    response = JitoBundleResponse(
        bundle_id="test_bundle_123",
        accepted=True,
        rejection_reason=None,
    )
    
    assert response.bundle_id == "test_bundle_123"
    assert response.accepted == True
    assert response.rejection_reason is None
    
    # Test rejected response
    rejected = JitoBundleResponse(
        bundle_id="",
        accepted=False,
        rejection_reason="tip_too_low",
    )
    
    assert rejected.accepted == False
    assert rejected.rejection_reason == "tip_too_low"
    
    log("[jito_bundle_smoke] Test 2 PASSED: Jito data structures work")
    return True

def test_bundle_construction():
    """Test 3: Test bundle construction logic."""
    log("[jito_bundle_smoke] Testing bundle construction...")
    
    from execution.jito_bundle_executor import (
        build_buy_bundle,
        calculate_tip_amount,
        JitoClient,
        JitoBundleRequest,
    )
    from execution.jito_structs import JitoConfig
    from execution.jito_structs import Pubkey
    
    # Create mock swap instruction
    class MockIx:
        def __init__(self, data=b"swap_instruction"):
            self.data = data
    
    swap_ix = MockIx()
    payer = Pubkey.from_string("11111111111111111111111111111111")
    tip_account = Pubkey.from_string("22222222222222222222222222222222")
    
    bundle = build_buy_bundle(
        swap_instruction=swap_ix,
        payer_wallet=payer,
        tip_account=tip_account,
        tip_amount_lamports=10000,
    )
    
    assert isinstance(bundle, JitoBundleRequest)
    assert len(bundle.instructions) == 2
    assert bundle.tip_amount_lamports == 10000
    assert bundle.tip_account == tip_account
    
    # Test tip calculation
    config = JitoConfig(
        enabled=True,
        tip_multiplier=1.2,
        min_tip_lamports=5000,
        max_tip_lamports=50000,
    )
    
    # Normal case
    tip = calculate_tip_amount(10000, config)  # 10000 * 1.2 = 12000
    assert tip == 12000
    
    # Below minimum
    tip = calculate_tip_amount(1000, config)  # 1000 * 1.2 = 1200, but min is 5000
    assert tip == 5000
    
    # Above maximum
    tip = calculate_tip_amount(100000, config)  # 100000 * 1.2 = 120000, max is 50000
    assert tip == 50000
    
    log("[jito_bundle_smoke] Test 3 PASSED: Bundle construction works")
    return True

async def test_jito_client_mock():
    """Test 4: Test JitoClient in mock mode."""
    log("[jito_bundle_smoke] Testing JitoClient mock mode...")
    
    from execution.jito_bundle_executor import JitoClient
    from execution.jito_structs import JitoConfig, JitoTipAccount
    from execution.jito_structs import Pubkey
    
    config = JitoConfig(
        enabled=True,
        endpoint="https://mock.block-engine.jito.wtf",
        tip_multiplier=1.0,
        min_tip_lamports=1000,
        max_tip_lamports=10000,
    )
    
    client = JitoClient(config=config)
    
    # Mock the get_tip_accounts method
    async def mock_get_tip_accounts():
        return [
            JitoTipAccount(
                account=Pubkey.from_string("tipYkqE4PLqPjV5SqB5Q4b2rT1VJvGpV7Zk7xrYx"),
                lamports_per_signature=10000,
            )
        ]
    
    client.get_tip_accounts = mock_get_tip_accounts
    
    # Test tip floor
    tip_floor = await client.get_tip_lamports_floor()
    assert tip_floor == 10000
    
    log("[jito_bundle_smoke] Test 4 PASSED: JitoClient mock mode works")
    return True

def test_rejection_handling():
    """Test 5: Test bundle rejection handling."""
    log("[jito_bundle_smoke] Testing bundle rejection handling...")
    
    from execution.jito_bundle_executor import JitoClient
    from execution.jito_structs import JitoConfig, JitoBundleResponse
    from integration.reject_reasons import JITOBUNDLE_REJECTED
    
    # Test rejected response
    rejected_response = JitoBundleResponse(
        bundle_id="",
        accepted=False,
        rejection_reason="Bundle was rejected due to low tip",
    )
    
    assert rejected_response.accepted == False
    assert rejected_response.rejection_reason is not None
    
    # Test timeout response
    timeout_response = JitoBundleResponse(
        bundle_id="",
        accepted=False,
        rejection_reason="timeout",
    )
    
    assert timeout_response.rejection_reason == "timeout"
    
    log("[jito_bundle_smoke] Test 5 PASSED: Rejection handling works")
    return True

def test_config_validation():
    """Test 6: Test JitoConfig validation."""
    log("[jito_bundle_smoke] Testing JitoConfig validation...")
    
    from execution.jito_structs import JitoConfig
    
    # Test invalid tip multiplier
    try:
        JitoConfig(tip_multiplier=-1.0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    # Test min > max
    try:
        JitoConfig(min_tip_lamports=100000, max_tip_lamports=1000)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    # Test valid config
    config = JitoConfig(
        enabled=False,
        tip_multiplier=1.5,
        min_tip_lamports=5000,
        max_tip_lamports=50000,
    )
    
    assert config.enabled == False
    assert config.tip_multiplier == 1.5
    
    log("[jito_bundle_smoke] Test 6 PASSED: Config validation works")
    return True

async def run_async_tests():
    """Run all async mock tests."""
    tests = [
        test_jito_client_mock,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            log(f"[jito_bundle_smoke] FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    return passed, failed

def main():
    log("[jito_bundle_smoke] Starting PR-G.4 smoke tests (mock mode)...")
    
    # Run sync tests
    sync_tests = [
        test_jito_reasons_known,
        test_jito_structs,
        test_bundle_construction,
        test_rejection_handling,
        test_config_validation,
    ]
    
    passed = 0
    failed = 0
    
    for test in sync_tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            log(f"[jito_bundle_smoke] FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Run async tests
    async_passed, async_failed = asyncio.run(run_async_tests())
    passed += async_passed
    failed += async_failed
    
    log(f"[jito_bundle_smoke] Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        log("[jito_bundle_smoke] OK")
        return 0
    else:
        log("[jito_bundle_smoke] FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
PYTHON_IMPORT
