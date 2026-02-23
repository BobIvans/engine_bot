#!/usr/bin/env bash
set -eo pipefail
# Smoke test for PR-X.1 State Reconciler (Watchdog).
# Tests the StateReconciler class and balance reconciliation logic.
# NOTE: This test runs in MOCK mode - no real network calls.

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from script
project_root="$(dirname "$SCRIPT_DIR")"

echo "project_root: $project_root" >&2

# Add project to PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}:$project_root"

# Import the state reconciler module
python3 << 'PYTHON_IMPORT'
import sys
import json
from datetime import datetime

def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

def test_balance_adjustment_struct():
    """Test 1: Test BalanceAdjustment dataclass."""
    log("[state_reconciler_smoke] Testing BalanceAdjustment dataclass...")
    
    from monitoring.state_reconciler import BalanceAdjustment, AdjustmentReason
    
    # Create an adjustment
    adj = BalanceAdjustment(
        timestamp=datetime.utcnow(),
        local_balance_lamports_before=1000000000,
        onchain_balance_lamports=1050000000,
        delta_lamports=50000000,
        reason="missed_tx",
        tx_signatures=["sig1", "sig2"],
        adjusted=True,
    )
    
    # Verify fields
    assert adj.local_balance_lamports_before == 1000000000
    assert adj.onchain_balance_lamports == 1050000000
    assert adj.delta_lamports == 50000000
    assert adj.reason == "missed_tx"
    assert len(adj.tx_signatures) == 2
    assert adj.adjusted == True
    assert adj.abs_delta == 50000000
    
    # Test to_dict
    adj_dict = adj.to_dict()
    assert adj_dict["local_balance_lamports_before"] == 1000000000
    assert adj_dict["delta_lamports"] == 50000000
    assert adj_dict["reason"] == "missed_tx"
    
    log("[state_reconciler_smoke] Test 1 PASSED: BalanceAdjustment works")
    return True

def test_reconciler_config():
    """Test 2: Test ReconcilerConfig validation."""
    log("[state_reconciler_smoke] Testing ReconcilerConfig...")
    
    from monitoring.state_reconciler import ReconcilerConfig
    
    # Valid config
    config = ReconcilerConfig(
        enabled=True,
        interval_seconds=300,
        warning_threshold_lamports=5000000,
        critical_threshold_lamports=50000000,
        max_delta_without_alert_lamports=1000000,
    )
    
    assert config.enabled == True
    assert config.interval_seconds == 300
    assert config.warning_threshold_lamports == 5000000
    
    # Test invalid config (warning > critical)
    try:
        ReconcilerConfig(
            warning_threshold_lamports=100000000,
            critical_threshold_lamports=50000000,
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    
    log("[state_reconciler_smoke] Test 2 PASSED: ReconcilerConfig works")
    return True

def test_state_reconciler():
    """Test 3: Test StateReconciler logic."""
    log("[state_reconciler_smoke] Testing StateReconciler...")
    
    from monitoring.state_reconciler import StateReconciler, ReconcilerConfig
    
    # Mock RPC client
    class MockRPCClient:
        def __init__(self, balance):
            self._balance = balance
        
        async def get_balance(self, pubkey):
            class Response:
                def __init__(self, value):
                    self.value = value
            return Response(self._balance)
    
    # Mock portfolio state
    class MockPortfolioState:
        def __init__(self, balance):
            self.bankroll_lamports = balance
            self.bankroll = balance / 1_000_000_000
    
    # Create reconciler with discrepancy
    portfolio = MockPortfolioState(1000000000)  # 1 SOL local
    rpc = MockRPCClient(1050000000)  # 1.05 SOL on-chain (discrepancy!)
    
    config = ReconcilerConfig(
        warning_threshold_lamports=5000000,
        critical_threshold_lamports=50000000,
        max_delta_without_alert_lamports=1000000,
    )
    
    reconciler = StateReconciler(
        rpc_client=rpc,
        wallet_pubkey="mock_pubkey",
        portfolio_state=portfolio,
        config=config,
        dry_run=True,  # Don't apply in test
    )
    
    # Run reconciliation
    adjustment = None
    import asyncio
    
    async def run_test():
        nonlocal adjustment
        adjustment = await reconciler.check_and_reconcile()
    
    asyncio.run(run_test())
    
    # Verify adjustment was created
    assert adjustment is not None, "Adjustment should be created"
    assert adjustment.delta_lamports == 50000000, f"Delta should be 50M, got {adjustment.delta_lamports}"
    assert adjustment.local_balance_lamports_before == 1000000000
    assert adjustment.onchain_balance_lamports == 1050000000
    assert adjustment.adjusted == False  # dry_run=True
    
    log(f"[state_reconciler_smoke] Adjustment created: delta={adjustment.delta_lamports}")
    log("[state_reconciler_smoke] Test 3 PASSED: StateReconciler works")
    return True

def test_no_adjustment_below_threshold():
    """Test 4: No adjustment when delta is below threshold."""
    log("[state_reconciler_smoke] Testing threshold behavior...")
    
    from monitoring.state_reconciler import StateReconciler, ReconcilerConfig
    
    # Mock RPC client with small discrepancy
    class MockRPCClient:
        def __init__(self, balance):
            self._balance = balance
        
        async def get_balance(self, pubkey):
            class Response:
                def __init__(self, value):
                    self.value = value
            return Response(self._balance)
    
    # Mock portfolio state
    class MockPortfolioState:
        def __init__(self, bankroll_lamports=0, **kwargs):
            self.bankroll_lamports = bankroll_lamports
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    # Create reconciler with small discrepancy (500K lamports = 0.0005 SOL)
    portfolio = MockPortfolioState(bankroll_lamports=1000000000)
    rpc = MockRPCClient(balance=1000500000)  # Only 500K more on-chain
    
    config = ReconcilerConfig(
        warning_threshold_lamports=5000000,
        critical_threshold_lamports=50000000,
        max_delta_without_alert_lamports=1000000,  # Ignore < 1M
    )
    
    reconciler = StateReconciler(
        rpc_client=rpc,
        wallet_pubkey="mock_pubkey",
        portfolio_state=portfolio,
        config=config,
    )
    
    # Run reconciliation
    adjustment = None
    
    import asyncio
    
    async def run_test():
        nonlocal adjustment
        adjustment = await reconciler.check_and_reconcile()
    
    asyncio.run(run_test())
    
    # Verify NO adjustment was created (delta below threshold)
    assert adjustment is None, "No adjustment should be created below threshold"
    
    log("[state_reconciler_smoke] Test 4 PASSED: Threshold behavior works")
    return True

def test_alert_level():
    """Test 5: Test alert level determination."""
    log("[state_reconciler_smoke] Testing alert level determination...")
    
    from monitoring.state_reconciler import StateReconciler, ReconcilerConfig, BalanceAdjustment
    from datetime import datetime
    
    config = ReconcilerConfig(
        warning_threshold_lamports=5000000,
        critical_threshold_lamports=50000000,
        max_delta_without_alert_lamports=1000000,
    )
    
    # Mock minimal objects
    class MockRPCClient:
        pass
    
    class MockPortfolioState:
        pass
    
    reconciler = StateReconciler(
        rpc_client=MockRPCClient(),
        wallet_pubkey="mock",
        portfolio_state=MockPortfolioState(),
        config=config,
    )
    
    # Test INFO level (below warning)
    adj_info = BalanceAdjustment(
        timestamp=datetime.utcnow(),
        local_balance_lamports_before=1000000000,
        onchain_balance_lamports=1002000000,
        delta_lamports=2000000,  # 2M - below warning
        reason="unknown",
    )
    assert reconciler.get_alert_level(adj_info) == "INFO"
    
    # Test WARNING level
    adj_warning = BalanceAdjustment(
        timestamp=datetime.utcnow(),
        local_balance_lamports_before=1000000000,
        onchain_balance_lamports=1005000000,
        delta_lamports=5000000,  # 5M - at warning threshold
        reason="unknown",
    )
    assert reconciler.get_alert_level(adj_warning) == "WARNING"
    
    # Test CRITICAL level
    adj_critical = BalanceAdjustment(
        timestamp=datetime.utcnow(),
        local_balance_lamports_before=1000000000,
        onchain_balance_lamports=1050000000,
        delta_lamports=50000000,  # 50M - at critical threshold
        reason="unknown",
    )
    assert reconciler.get_alert_level(adj_critical) == "CRITICAL"
    
    log("[state_reconciler_smoke] Test 5 PASSED: Alert levels work")
    return True

def test_adjustment_export():
    """Test 6: Test adjustment export functionality."""
    log("[state_reconciler_smoke] Testing adjustment export...")
    
    from monitoring.state_reconciler import StateReconciler, ReconcilerConfig
    
    class MockRPCClient:
        pass
    
    class MockPortfolioState:
        pass
    
    config = ReconcilerConfig()
    
    reconciler = StateReconciler(
        rpc_client=MockRPCClient(),
        wallet_pubkey="mock",
        portfolio_state=MockPortfolioState(),
        config=config,
    )
    
    # Add some mock adjustments
    from datetime import datetime
    
    adj1 = type('Adj', (), {
        'to_dict': lambda self: {"id": 1, "delta": 1000},
    })()
    adj2 = type('Adj', (), {
        'to_dict': lambda self: {"id": 2, "delta": 2000},
    })()
    
    reconciler._adjustments = [adj1, adj2]
    
    # Test export
    exported = reconciler.export_adjustments()
    assert len(exported) == 2
    assert exported[0]["id"] == 1
    assert exported[1]["id"] == 2
    
    # Test recent adjustments
    recent = reconciler.get_recent_adjustments(limit=1)
    assert len(recent) == 1
    
    log("[state_reconciler_smoke] Test 6 PASSED: Export functionality works")
    return True

def main():
    log("[state_reconciler_smoke] Starting PR-X.1 smoke tests (mock mode)...")
    
    tests = [
        test_balance_adjustment_struct,
        test_reconciler_config,
        test_state_reconciler,
        test_no_adjustment_below_threshold,
        test_alert_level,
        test_adjustment_export,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            log(f"[state_reconciler_smoke] FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    log(f"[state_reconciler_smoke] Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        log("[state_reconciler_smoke] OK")
        return 0
    else:
        log("[state_reconciler_smoke] FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
PYTHON_IMPORT
