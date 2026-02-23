#!/bin/bash
# scripts/rpc_smoke.sh
# Smoke test for RPC batching and caching (PR-T.1)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running rpc smoke..." >&2

# Create temp directory for test
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Create Python test script
cat > "$TEMP_DIR/test_rpc.py" << 'PYEOF'
#!/usr/bin/env python3
"""RPC Batching and Caching Smoke Test (PR-T.1)"""
import sys
import json
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, '.')

from ingestion.rpc.client import SmartRpcClient
from ingestion.rpc.batcher import RpcBatcher, BatchItem
from ingestion.rpc.cache import RpcCache


def test_batching():
    """Test that batching works: 150 requests -> 2 HTTP calls"""
    logger.info("Testing batching: 150 requests...")
    
    http_calls = []
    
    def mock_http(requests):
        http_calls.append(len(requests))
        # Return mock response for each request
        responses = []
        for req in requests:
            method = req.get('method', '')
            if method == 'getBalance':
                responses.append({'result': {'value': 1000000000}})
            elif method == 'getAccountInfo':
                responses.append({'result': {'value': {'data': ['test'], 'owner': 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'}}})
            else:
                responses.append({'result': {}})
        return responses
    
    # Create client with batch delay of 50ms to force batching
    client = SmartRpcClient(
        http_callable=mock_http,
        batch_delay_ms=50.0,
        cache_ttl=60,
    )
    
    # Queue 150 requests (should trigger 2 batches: 100 + 50)
    futures = []
    for i in range(150):
        future = client.request(
            method='getBalance',
            params=[f'pubkey{i}'],
            key=f'pubkey{i}',  # Unique key to prevent caching
            ttl=60,
        )
        futures.append(future)
    
    # Flush and wait for completion
    client.flush()
    
    # Collect results
    for f in futures:
        _ = f.get()
    
    # Verify we got 2 HTTP calls (100 + 50)
    expected_calls = 2
    actual_calls = len(http_calls)
    
    if actual_calls == expected_calls:
        logger.info(f"Batching check: {150} requests -> {actual_calls} http calls (OK)")
        return True
    else:
        logger.error(f"Batching FAILED: {150} requests -> {actual_calls} http calls (expected {expected_calls})")
        return False


def test_caching():
    """Test that caching works: repeated requests hit cache"""
    logger.info("Testing cache: 100 requests with cache hits...")
    
    http_calls = []
    
    def mock_http(requests):
        http_calls.append(len(requests))
        responses = []
        for req in requests:
            responses.append({'result': {'value': 1000000000}})
        return responses
    
    # Create client
    client = SmartRpcClient(
        http_callable=mock_http,
        batch_delay_ms=50.0,
        cache_ttl=60,
    )
    
    # First batch of 10 unique requests (cache miss)
    futures1 = []
    for i in range(10):
        future = client.request(
            method='getBalance',
            params=[f'pubkey{i}'],
            key=f'unique{i}',
            ttl=60,
        )
        futures1.append(future)
    
    client.flush()
    for f in futures1:
        _ = f.get()
    
    # Clear http_calls tracker
    http_calls.clear()
    
    # Now repeat the same 10 requests (should all be cache hits)
    futures2 = []
    for i in range(10):
        result = client.request(
            method='getBalance',
            params=[f'pubkey{i}'],
            key=f'unique{i}',
            ttl=60,
        )
        futures2.append(result)
    
    client.flush()
    for f in futures2:
        _ = f.get()
    
    # Verify no HTTP calls were made for cached requests
    if len(http_calls) == 0:
        logger.info(f"Cache check: Hit rate 100% on retry (OK)")
        return True
    else:
        logger.error(f"Cache FAILED: Expected 0 HTTP calls, got {len(http_calls)}")
        return False


def test_ttl_expiration():
    """Test that TTL-based expiration works"""
    logger.info("Testing TTL expiration...")
    
    def mock_http(requests):
        responses = []
        for req in requests:
            responses.append({'result': {'value': 1000}})
        return responses
    
    # Create cache with 100ms TTL
    cache = RpcCache(default_ttl=0.1)  # 100ms
    
    # Set a value with 1 second TTL
    cache.set('key1', 'value1', ttl=1)
    
    # Should be there
    assert cache.get('key1') == 'value1', "Cache miss before expiration"
    
    # Wait for expiration
    time.sleep(1.1)
    
    # Should be gone
    assert cache.get('key1') is None, "Cache should be expired"
    
    logger.info("TTL expiration check: OK")
    return True


def test_exponential_backoff():
    """Test that exponential backoff works on 429 errors"""
    logger.info("Testing exponential backoff...")
    
    call_count = [0]
    
    def adaptive_http(requests):
        call_count[0] += 1
        if call_count[0] <= 3:
            raise Exception("429 Too Many Requests")
        responses = []
        for req in requests:
            responses.append({'result': {}})
        return responses
    
    client = SmartRpcClient(
        http_callable=adaptive_http,
        max_retries=5,
        initial_delay_ms=10,  # Fast for testing
    )
    
    try:
        future = client.request(
            method='getBalance',
            params=['test'],
            key='test_key',
            ttl=60,
        )
        client.flush()
        result = future.get()
        
        # Should have made 4 attempts (3 fails + 1 success)
        if call_count[0] == 4:
            logger.info("Exponential backoff check: OK (4 attempts)")
            return True
        else:
            logger.error(f"Exponential backoff FAILED: Expected 4 attempts, got {call_count[0]}")
            return False
    except Exception as e:
        logger.error(f"Exponential backoff FAILED with error: {e}")
        return False


def test_cache_metrics():
    """Test cache metrics reporting"""
    logger.info("Testing cache metrics...")
    
    def mock_http(requests):
        responses = []
        for req in requests:
            responses.append({'result': {'value': 1000}})
        return responses
    
    cache = RpcCache(default_ttl=60)
    
    # Make some gets
    cache.set('a', 1)
    cache.set('b', 2)
    _ = cache.get('a')  # hit
    _ = cache.get('c')  # miss (key doesn't exist)
    _ = cache.get('a')  # hit
    
    metrics = cache.get_metrics()
    
    assert metrics['hits'] == 2, f"Expected 2 hits, got {metrics['hits']}"
    assert metrics['misses'] == 1, f"Expected 1 miss, got {metrics['misses']}"
    assert metrics['size'] == 2, f"Expected size 2, got {metrics['size']}"
    
    logger.info("Cache metrics check: OK")
    return True


def main():
    """Run all tests"""
    tests = [
        ("Batching", test_batching),
        ("Caching", test_caching),
        ("TTL Expiration", test_ttl_expiration),
        ("Exponential Backoff", test_exponential_backoff),
        ("Cache Metrics", test_cache_metrics),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test {name} failed with exception: {e}")
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
        logger.info("[rpc_smoke] OK")
        sys.exit(0)
    else:
        logger.error(f"[rpc_smoke] FAILED ({failed}/{len(results)} tests)")
        sys.exit(1)


if __name__ == '__main__':
    main()
PYEOF

# Run the test
python3 "$TEMP_DIR/test_rpc.py"

echo "[rpc_smoke] OK" >&2
