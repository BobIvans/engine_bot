#!/bin/bash
# scripts/jito_smoke.sh
# Smoke test for Jito Bundle Stub & Fee Logic

set -e

GREEN='\033[0;32m'
NC='\033[0m'

pass() {
  echo -e "${GREEN}[jito_smoke] OK: $*${NC}" >&2
}

echo "[jito_smoke] Testing Jito bundle structures..." >&2

# Test 1: Pure logic tests (import modules)
echo "[jito_smoke] Testing pure logic..." >&2

python3 << 'PYEOF'
import sys
sys.path.insert(0, ".")

from strategy.jito_structs import (
    JitoBundle,
    TIP_ACCOUNTS,
    calculate_bundle_cost,
    validate_tip_account,
    JitoTipEstimator,
)

# Test 1: Create a bundle
print("Testing bundle creation...")
bundle = JitoBundle(
    transactions=["tx1_base64", "tx2_base64", "tx3_base64"],
    tip_lamports=100_000,
    strategy_tag="test-strategy",
)
print(f"Bundle ID: {bundle.bundle_id}")
print(f"Transactions: {len(bundle.transactions)}")
print(f"Tip: {bundle.tip_lamports:,} lamports")

# Verify bundle has required fields
assert bundle.bundle_id.startswith("bundle-"), "Bundle ID should start with 'bundle-'"
assert len(bundle.transactions) == 3, "Should have 3 transactions"
assert bundle.tip_lamports == 100_000, "Tip should be 100_000"
print("Bundle creation: PASS")

# Test 2: Verify TIP_ACCOUNTS exists
print("\nTesting TIP_ACCOUNTS...")
assert len(TIP_ACCOUNTS) > 0, "TIP_ACCOUNTS should not be empty"
print(f"TIP_ACCOUNTS count: {len(TIP_ACCOUNTS)}")
print("TIP_ACCOUNTS: PASS")

# Test 3: Validate tip account
print("\nTesting tip account validation...")
# Known tip account
assert validate_tip_account(TIP_ACCOUNTS[0]) == True, "Known tip account should validate"
# Unknown tip account
assert validate_tip_account("Unknown123") == False, "Unknown account should not validate"
print("Tip account validation: PASS")

# Test 4: Calculate bundle cost
print("\nTesting bundle cost calculation...")
cost = calculate_bundle_cost(bundle)
print(f"Total cost: {cost['total_cost_lamports']:,} lamports")
print(f"Network fees: {cost['network_fees_lamports']:,} lamports")
print(f"Jito tip: {cost['jito_tip_lamports']:,} lamports")
assert cost["jito_tip_lamports"] == 100_000, "Jito tip should match bundle tip"
assert cost["num_transactions"] == 3, "Should have 3 transactions"
print("Bundle cost calculation: PASS")

# Test 5: Tip estimator
print("\nTesting tip estimator...")
for urgency in ["slow", "normal", "fast", "urgent"]:
    tip = JitoTipEstimator.estimate_optimal_tip(urgency)
    print(f"  {urgency}: {tip:,} lamports")
    assert JitoTipEstimator.validate_tip_amount(tip), f"Tip {tip} should be valid"
print("Tip estimator: PASS")

print("\nAll pure logic tests passed!")
PYEOF

pass "Pure logic tests"

# Test 2: Execution stub tests
echo "[jito_smoke] Testing execution stub..." >&2

python3 << 'PYEOF'
import sys
sys.path.insert(0, ".")

from execution.jito_stub import JitoExecutionStub, JitoSimulator

# Test 1: Create stub
print("Testing stub creation...")
stub = JitoExecutionStub(failure_rate=0.0, simulate_latency_ms=10)
print(f"Failure rate: {stub.failure_rate}")
print(f"Latency: {stub.simulate_latency_ms}ms")
print("Stub creation: PASS")

# Test 2: Build bundle
print("\nTesting bundle building...")
bundle = stub.build_bundle(
    transactions=["sig1", "sig2", "sig3"],
    tip_lamports=100_000,
    strategy_tag="smoke-test",
)
assert bundle.tip_lamports == 100_000, "Tip should be 100_000"
print(f"Bundle tip: {bundle.tip_lamports:,} lamports")
print("Bundle building: PASS")

# Test 3: Simulate send (with no failures)
print("\nTesting simulate_send (0% failure)...")
result = stub.simulate_send(bundle, failure_rate=0.0)
print(f"Status: {result['status']}")
print(f"Bundle ID: {result['bundle_id']}")
print(f"Bribe: {result['bribe_lamports']:,} lamports")
print(f"Accepted in block: {result['accepted_in_block']}")

# Verify bribe amount
assert result["bribe_lamports"] == 100_000, f"Bribe should be 100_000, got {result['bribe_lamports']}"
# Verify status
assert result["status"] == "landed", f"Status should be 'landed', got {result['status']}"
print("Simulate send (no failure): PASS")

# Test 4: Verify stats
print("\nTesting stub statistics...")
stats = stub.get_stats()
print(f"Bundles sent: {stats['bundles_sent']}")
print(f"Bundles landed: {stats['bundles_landed']}")
print(f"Total tips: {stats['total_tips_lamports']:,}")
assert stats["bundles_landed"] == 1, "Should have landed 1 bundle"
assert stats["total_tips_lamports"] == 100_000, "Total tips should be 100_000"
print("Stub statistics: PASS")

# Test 5: Simulator
print("\nTesting JitoSimulator...")
sim = JitoSimulator(failure_rate=0.0)
sim_result = sim.simulate_single_bundle(["tx1", "tx2"], tip_lamports=50_000)
print(f"Simulator status: {sim_result['status']}")
print(f"Simulator bribe: {sim_result['bribe_lamports']:,}")
assert sim_result["bribe_lamports"] == 50_000, "Bribe should be 50_000"
print("JitoSimulator: PASS")

print("\nAll execution stub tests passed!")
PYEOF

pass "Execution stub tests"

# Test 3: Verify fee accounting
echo "[jito_smoke] Verifying fee accounting..." >&2

python3 << 'PYEOF'
import sys
sys.path.insert(0, ".")

from strategy.jito_structs import JitoBundle, calculate_bundle_cost
from execution.jito_stub import JitoExecutionStub

# Test: Verify bribe is correctly separated from network fees
print("Testing PnL integrity (separate bribe from network fees)...")
bundle = JitoBundle(
    transactions=["tx1", "tx2", "tx3", "tx4", "tx5"],
    tip_lamports=150_000,
)

cost = calculate_bundle_cost(bundle)
print(f"Total cost: {cost['total_cost_lamports']:,} lamports")
print(f"  Network fees: {cost['network_fees_lamports']:,} lamports")
print(f"  Jito bribe: {cost['jito_tip_lamports']:,} lamports")

# Verify separation
assert cost["jito_tip_lamports"] == 150_000, "Jito bribe should be 150_000"
assert cost["network_fees_lamports"] > 0, "Network fees should be positive"
assert cost["total_cost_lamports"] == cost["network_fees_lamports"] + cost["jito_tip_lamports"]

print("Fee accounting verified!")

# Test: JSON serializable
print("\nTesting JSON serializability...")
stub = JitoExecutionStub(failure_rate=0.0)
result = stub.simulate_send(bundle)

import json
json_output = json.dumps(result, indent=2)
print("JSON output (first 200 chars):")
print(json_output[:200] + "..." if len(json_output) > 200 else json_output)

# Verify all values are JSON-serializable
for key, value in result.items():
    if value is not None:
        json.dumps({key: value})  # Will raise if not serializable

print("JSON serializability: PASS")
print("\nPnL integrity verified!")
PYEOF

pass "Fee accounting verified"

echo "[jito_smoke] All tests passed!" >&2
echo -e "${GREEN}[jito_smoke] OK ✅${NC}" >&2

exit 0
