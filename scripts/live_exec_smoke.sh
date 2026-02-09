#!/bin/bash
# scripts/live_exec_smoke.sh
# PR-G.1 Transaction Builder Adapter & Simulation - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"

echo "[live_exec_smoke] Starting live execution smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import json
import os

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

# Mock requests before importing the executor
import unittest.mock as mock

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [live_exec] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [live_exec] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[live_exec_smoke] Testing executor interface...", file=sys.stderr)

from execution.live_executor import LiveExecutor, NoOpLiveExecutor
from execution.solana_executor import create_live_executor

# Test 1: NoOpLiveExecutor
noop = NoOpLiveExecutor()
test_case("noop_created", noop is not None)

# Test 2: NoOpLiveExecutor returns disabled
result = noop.build_swap_tx(
    wallet="test_wallet",
    input_mint="SOL",
    output_mint="USDC",
    amount_lamports=1000000,
)
test_case("noop_build_disabled", result.get("success") == False)
test_case("noop_build_error", "not enabled" in result.get("error", ""))

result = noop.simulate_tx(tx_base64="test")
test_case("noop_sim_disabled", result.get("success") == False)

result = noop.get_quote(
    input_mint="SOL",
    output_mint="USDC",
    amount_lamports=1000000,
)
test_case("noop_quote_disabled", result.get("success") == False)

# Test 3: Factory with disabled config
config_disabled = {"execution": {"live_enabled": False}}
disabled_exec = create_live_executor(config_disabled)
test_case("factory_disabled", isinstance(disabled_exec, NoOpLiveExecutor))

print("[live_exec_smoke] Testing JupiterSolanaExecutor with mocks...", file=sys.stderr)

# Mock Jupiter Quote response
JUPITER_QUOTE_RESPONSE = {
    "inputMint": "So11111111111111111111111111111111111111112",
    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "inAmount": "1000000000",
    "outAmount": "230000000",
    "priceImpactPct": "0.01",
    "routePlan": [{"swapInfo": {"label": "Jupiter"}}],
}

# Mock Jupiter Swap response
JUPITER_SWAP_RESPONSE = {
    "success": True,
    "swapTransaction": "AQAAAA-test-transaction-base64",
    "otherTransactions": [],
}

# Mock RPC Simulate response
RPC_SIMULATE_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "value": {
            "err": None,
            "logs": ["Program 11111111111111111111111111111111 invoke [1]", "Program 11111111111111111111111111111111 success"],
            "unitsConsumed": 12345,
        }
    },
}

def create_mock_response(data):
    """Create a mock response object with the given data."""
    response = mock.MagicMock()
    response.raise_for_status = mock.MagicMock()
    response.json.return_value = data
    return response

def mock_post(url, **kwargs):
    """Mock post function that returns different responses based on URL."""
    if url.endswith("/quote"):
        return create_mock_response(JUPITER_QUOTE_RESPONSE)
    elif url.endswith("/swap"):
        return create_mock_response(JUPITER_SWAP_RESPONSE)
    else:
        # RPC simulateTransaction endpoint
        return create_mock_response(RPC_SIMULATE_RESPONSE)

# Test 4: JupiterSolanaExecutor with mocked requests
with mock.patch("execution.solana_executor.requests.Session") as MockSession:
    mock_session = mock.MagicMock()
    MockSession.return_value = mock_session
    mock_session.post = mock_post

    from execution.solana_executor import JupiterSolanaExecutor

    executor = JupiterSolanaExecutor()

    # Test 5: Get quote
    quote_result = executor.get_quote(
        input_mint="SOL",
        output_mint="USDC",
        amount_lamports=1000000000,
    )
    test_case("quote_success", quote_result.get("success") == True)
    test_case("quote_out_amount", quote_result.get("out_amount") == 230000000)

    # Test 6: Build swap transaction
    build_result = executor.build_swap_tx(
        wallet="test_wallet_addr",
        input_mint="SOL",
        output_mint="USDC",
        amount_lamports=1000000000,
    )
    test_case("build_success", build_result.get("success") == True)
    test_case("build_has_tx", len(build_result.get("tx_base64", "")) > 0)

    # Test 7: Simulate transaction
    sim_result = executor.simulate_tx(tx_base64="AQAAAA-test-transaction-base64")
    test_case("sim_success", sim_result.get("success") == True)
    test_case("sim_units", sim_result.get("units_consumed") == 12345)

print("[live_exec_smoke] Testing error handling...", file=sys.stderr)

# Test 8: Error handling
import requests

with mock.patch("execution.solana_executor.requests.Session") as MockSession:
    mock_session = mock.MagicMock()
    MockSession.return_value = mock_session

    # Simulate HTTP error (raise_for_status raises HTTPError)
    mock_response = mock.MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("HTTP 500")
    mock_session.post = mock.MagicMock(return_value=mock_response)

    from execution.solana_executor import JupiterSolanaExecutor

    executor = JupiterSolanaExecutor()
    result = executor.get_quote(
        input_mint="SOL",
        output_mint="USDC",
        amount_lamports=1000000,
    )
    test_case("http_error_handled", result.get("success") == False)

# Summary
print(f"\n[live_exec_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[live_exec_smoke] OK", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[live_exec_smoke] Smoke test completed." >&2
