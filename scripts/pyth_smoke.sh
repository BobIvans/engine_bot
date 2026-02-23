#!/bin/bash
# scripts/pyth_smoke.sh
# Smoke test for Pyth Price Feeds (PR-T.3)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running pyth smoke..." >&2

# Create temp directory for test
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Create Python test script
cat > "$TEMP_DIR/test_pyth.py" << 'PYEOF'
#!/usr/bin/env python3
"""Pyth Price Feeds Smoke Test (PR-T.3)"""
import sys
import json
import logging
from unittest.mock import Mock

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, '.')

from ingestion.market.pyth import PythClient, PriceData
from ingestion.market.pyth_ids import FEED_IDS, get_feed_id


def test_feed_ids():
    """Test that feed IDs are correctly defined."""
    logger.info("Testing feed IDs registry...")
    
    # Check SOL/USD feed ID
    sol_id = get_feed_id("SOL/USD")
    expected_sol = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
    assert sol_id == expected_sol, f"SOL/USD ID mismatch: {sol_id} != {expected_sol}"
    
    # Check USDC/USD feed ID
    usdc_id = get_feed_id("USDC/USD")
    expected_usdc = "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a"
    assert usdc_id == expected_usdc, f"USDC/USD ID mismatch: {usdc_id} != {expected_usdc}"
    
    logger.info("Feed IDs registry: OK")
    return True


def test_price_normalization():
    """Test price normalization with mock data."""
    logger.info("Testing price normalization...")
    
    # Load mock response
    fixture_path = "integration/fixtures/pyth/mock_hermes_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    # Create mock HTTP callable
    def mock_get(url):
        mock_resp = Mock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = Mock()
        return mock_resp
    
    # Create client
    client = PythClient(cache_ttl=60)
    
    # Fetch SOL/USD
    price_data = client.fetch_price("SOL/USD", http_callable=mock_get)
    
    assert price_data is not None, "Price data is None"
    assert price_data.symbol == "SOL/USD", f"Symbol mismatch: {price_data.symbol}"
    assert price_data.price == 150.50, f"Price mismatch: {price_data.price} != 150.50"
    assert price_data.conf == 0.05, f"Confidence mismatch: {price_data.conf} != 0.05"
    assert price_data.status == "trading", f"Status mismatch: {price_data.status}"
    assert price_data.ts == 1707349200, f"Timestamp mismatch: {price_data.ts}"
    
    logger.info(f"Mock price parsed: {price_data.price:.2f} USD (OK)")
    
    # Check confidence interval
    is_safe = price_data.is_safe(threshold=0.01)
    assert is_safe, f"Price marked as unsafe: conf/price = {price_data.conf/price_data.price}"
    logger.info(f"Confidence check: {price_data.conf:.2f} < {price_data.price:.2f} (OK)")
    
    return True


def test_price_caching():
    """Test that prices are cached."""
    logger.info("Testing price caching...")
    
    # Load mock response
    fixture_path = "integration/fixtures/pyth/mock_hermes_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    call_count = [0]
    
    def mock_get(url):
        call_count[0] += 1
        mock_resp = Mock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = Mock()
        return mock_resp
    
    # Create client with short cache TTL
    client = PythClient(cache_ttl=1)
    
    # First call (should hit API)
    price1 = client.fetch_price("SOL/USD", http_callable=mock_get)
    assert call_count[0] == 1, f"First call count: {call_count[0]}"
    
    # Second call (should hit cache)
    price2 = client.fetch_price("SOL/USD", http_callable=mock_get)
    assert call_count[0] == 1, f"Second call count (should be cached): {call_count[0]}"
    
    # Wait for cache expiration
    import time
    time.sleep(1.1)
    
    # Third call (should hit API again)
    price3 = client.fetch_price("SOL/USD", http_callable=mock_get)
    assert call_count[0] == 2, f"Third call count: {call_count[0]}"
    
    logger.info("Price caching: OK")
    return True


def test_stablecoin_detection():
    """Test stablecoin detection."""
    logger.info("Testing stablecoin detection...")
    
    from ingestion.market.pyth_ids import is_stablecoin
    
    assert is_stablecoin("USDC/USD") == True
    assert is_stablecoin("USDT/USD") == True
    assert is_stablecoin("SOL/USD") == False
    
    logger.info("Stablecoin detection: OK")
    return True


def test_error_handling():
    """Test graceful error handling."""
    logger.info("Testing error handling...")
    
    def mock_fail(url):
        raise Exception("Network error")
    
    client = PythClient()
    
    # Should return None, not raise exception
    result = client.fetch_price("SOL/USD", http_callable=mock_fail)
    assert result is None, f"Expected None on error, got {result}"
    
    logger.info("Error handling: OK")
    return True


def main():
    """Run all tests."""
    tests = [
        ("Feed IDs", test_feed_ids),
        ("Price Normalization", test_price_normalization),
        ("Price Caching", test_price_caching),
        ("Stablecoin Detection", test_stablecoin_detection),
        ("Error Handling", test_error_handling),
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
        logger.info("[pyth_smoke] OK")
        sys.exit(0)
    else:
        logger.error(f"[pyth_smoke] FAILED ({failed}/{len(results)} tests)")
        sys.exit(1)


if __name__ == '__main__':
    main()
PYEOF

# Run the test
python3 "$TEMP_DIR/test_pyth.py"

echo "[pyth_smoke] OK" >&2
