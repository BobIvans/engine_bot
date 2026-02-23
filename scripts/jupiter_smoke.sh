#!/bin/bash
# scripts/jupiter_smoke.sh
# Smoke test for Jupiter Quote API Client (PR-T.5)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running jupiter smoke..." >&2

# Create temp directory for test
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Create Python test script
cat > "$TEMP_DIR/test_jupiter.py" << 'PYEOF'
#!/usr/bin/env python3
"""Jupiter Quote API Smoke Test (PR-T.5)"""
import sys
import json
import logging
from unittest.mock import Mock

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, '.')

from ingestion.dex.jupiter import JupiterClient
from ingestion.dex.models import QuoteResponse, SwapRequest


def test_quote_parsing():
    """Test quote parsing from mock response."""
    logger.info("Testing quote parsing...")
    
    # Load mock response
    fixture_path = "integration/fixtures/jupiter/mock_quote_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    call_count = [0]
    
    def mock_get(url, params):
        call_count[0] += 1
        return mock_response
    
    # Create client
    client = JupiterClient()
    
    # Request: SOL -> USDC, 1 SOL (1e9 atomic units)
    quote = client.get_quote(
        input_mint="So11111111111111111111111111111111111111112",  # SOL
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        amount_atomic=1000000000,  # 1 SOL
        slippage_bps=50,
        http_callable=mock_get,
    )
    
    assert quote is not None, "Quote is None"
    assert quote.in_amount == 1000000000, f"in_amount mismatch: {quote.in_amount}"
    assert quote.out_amount == 150500000, f"out_amount mismatch: {quote.out_amount}"
    assert quote.input_mint == "So11111111111111111111111111111111111111112"
    assert quote.output_mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    # Verify decimal conversion (SOL = 9 decimals, USDC = 6 decimals)
    sol_amount = quote.get_in_amount_decimal(decimals=9)
    usdc_amount = quote.get_out_amount_decimal(decimals=6)
    
    assert abs(sol_amount - 1.0) < 0.001, f"SOL amount mismatch: {sol_amount}"
    assert abs(usdc_amount - 150.5) < 0.01, f"USDC amount mismatch: {usdc_amount}"
    
    logger.info(f"Mock quote parsed: {sol_amount:.2f} SOL -> {usdc_amount:.2f} USDC (OK)")
    
    return True


def test_price_impact():
    """Test price impact parsing and conversion."""
    logger.info("Testing price impact...")
    
    # Load mock response
    fixture_path = "integration/fixtures/jupiter/mock_quote_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    def mock_get(url, params):
        return mock_response
    
    client = JupiterClient()
    
    quote = client.get_quote(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_atomic=1000000000,
        http_callable=mock_get,
    )
    
    assert quote is not None, "Quote is None"
    
    # Check price impact percentage
    assert abs(quote.price_impact_pct - 0.001) < 0.0001, f"Impact pct mismatch: {quote.price_impact_pct}"
    
    # Check BPS conversion (0.001 = 0.1% = 10 bps)
    impact_bps = quote.get_price_impact_bps()
    assert impact_bps == 10, f"Impact bps mismatch: {impact_bps}"
    
    logger.info(f"Impact check: {quote.price_impact_pct:.3%} ({impact_bps} bps) (OK)")
    
    # Test slippage acceptable check
    assert quote.is_slippage_acceptable(max_slippage_bps=100) == True
    assert quote.is_slippage_acceptable(max_slippage_bps=5) == False
    
    return True


def test_route_plan():
    """Test route plan parsing."""
    logger.info("Testing route plan...")
    
    # Load mock response
    fixture_path = "integration/fixtures/jupiter/mock_quote_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    def mock_get(url, params):
        return mock_response
    
    client = JupiterClient()
    
    quote = client.get_quote(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_atomic=1000000000,
        http_callable=mock_get,
    )
    
    assert quote is not None, "Quote is None"
    assert len(quote.route_plan) == 1, f"Expected 1 route step, got {len(quote.route_plan)}"
    
    step = quote.route_plan[0]
    assert step.amm_key == "CAMMCzo5YL8w4Eaf39c9mW13t9Z3fQHTDB7Z4Yo7JrKm"
    assert step.label == "Raydium"
    assert step.in_amount == 1000000000
    assert step.out_amount == 150500000
    
    # Check DEXes used
    dexes = quote.get_dexes_used()
    assert len(dexes) == 1
    assert dexes[0] == "Raydium"
    
    # Check multi-DEX flag
    assert quote.is_multi_dex_route() == False
    
    logger.info(f"Route plan: {dexes} (OK)")
    
    return True


def test_no_route_error():
    """Test handling of 'no route' error."""
    logger.info("Testing no route error handling...")
    
    error_response = {
        "error": "No route found for this swap",
        "errorCode": "NO_ROUTE"
    }
    
    def mock_get(url, params):
        return error_response
    
    client = JupiterClient()
    
    quote = client.get_quote(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_atomic=1000000000,
        http_callable=mock_get,
    )
    
    assert quote is None, f"Expected None for no route, got {quote}"
    
    logger.info("No route error: OK (graceful degradation)")
    
    return True


def test_swap_request():
    """Test SwapRequest model."""
    logger.info("Testing SwapRequest model...")
    
    request = SwapRequest(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_atomic=1000000000,
        slippage_bps=50,
    )
    
    params = request.to_url_params()
    
    assert params["inputMint"] == "So11111111111111111111111111111111111111112"
    assert params["outputMint"] == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert params["amount"] == "1000000000"
    assert params["slippageBps"] == "50"
    
    logger.info("SwapRequest: OK")
    
    return True


def test_rate_limit_handling():
    """Test rate limit backoff."""
    logger.info("Testing rate limit handling...")
    
    call_count = [0]
    last_error = [None]
    
    def mock_get(url, params):
        call_count[0] += 1
        if call_count[0] < 3:
            from unittest.mock import Mock
            resp = Mock()
            resp.status_code = 429
            resp.text = "Too Many Requests"
            resp.raise_for_status.side_effect = Exception("Rate limited")
            raise Exception("Rate limited")
        return {"inAmount": "1000000000", "outAmount": "150500000", "priceImpactPct": "0.001"}
    
    client = JupiterClient(max_retries=3, initial_delay_ms=10)
    
    quote = client.get_quote(
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_atomic=1000000000,
        http_callable=mock_get,
    )
    
    assert quote is not None, "Quote should succeed after retries"
    assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"
    
    logger.info("Rate limit handling: OK")
    
    return True


def main():
    """Run all tests."""
    tests = [
        ("Quote Parsing", test_quote_parsing),
        ("Price Impact", test_price_impact),
        ("Route Plan", test_route_plan),
        ("No Route Error", test_no_route_error),
        ("SwapRequest", test_swap_request),
        ("Rate Limit Handling", test_rate_limit_handling),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    logger.info("")
    logger.info("=" * 50)
    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        logger.info(f"  {name}: {status}")
    
    logger.info("=" * 50)
    
    if failed == 0:
        logger.info("[jupiter_smoke] OK")
        sys.exit(0)
    else:
        logger.error(f"[jupiter_smoke] FAILED ({failed}/{len(results)} tests)")
        sys.exit(1)


if __name__ == '__main__':
    main()
PYEOF

# Run the test
python3 "$TEMP_DIR/test_jupiter.py"

echo "[jupiter_smoke] OK" >&2
