#!/bin/bash
# scripts/rpc_failover_smoke.sh
# Smoke test for RPC failover (PR-T.2)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running rpc failover smoke..." >&2

# Create temp directory for test
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Create Python test script
cat > "$TEMP_DIR/test_failover.py" << 'PYEOF'
#!/usr/bin/env python3
"""RPC Failover Smoke Test (PR-T.2)"""
import sys
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, '.')

from ingestion.rpc.client import SmartRpcClient
from ingestion.rpc.failover import FailoverManager
from ingestion.rpc.monitor import HealthMonitor


def test_failover():
    """Test automatic failover when main provider fails."""
    logger.info("Testing failover: Main fails, switch to Backup...")
    
    call_count = {}
    endpoint_history = []
    
    def mock_http(requests):
        """Mock HTTP that fails on Main, succeeds on Backup."""
        responses = []
        for req in requests:
            endpoint = req.get('endpoint', 'Unknown')
            call_count[endpoint] = call_count.get(endpoint, 0) + 1
            
            # Check if endpoint is Main (helius)
            if "helius" in str(endpoint).lower() or "main" in str(endpoint).lower():
                # Fail with 500 error
                endpoint_history.append((endpoint, "FAIL"))
                raise Exception("HTTP 500 Internal Server Error")
            else:
                # Success
                endpoint_history.append((endpoint, "SUCCESS"))
                responses.append({'result': {'value': 1000000000}})
        return responses
    
    # Create failover manager with two endpoints
    failover = FailoverManager()
    failover.add_endpoint("https://helius.main.rpc", priority=0, is_primary=True)
    failover.add_endpoint("https://public.backup.rpc", priority=1, is_primary=False)
    
    # Create client with failover
    client = SmartRpcClient(
        http_callable=mock_http,
        failover_manager=failover,
        cache_ttl=60,
    )
    
    # Track failover switches
    switch_detected = [False]
    original_switch = failover._switch_endpoint
    
    def track_switch(new_url):
        if new_url and "backup" in str(new_url).lower():
            switch_detected[0] = True
            logger.info("[rpc_failover_smoke] Switching to Backup...")
        return original_switch(new_url)
    
    failover._switch_endpoint = track_switch
    
    # First request should fail on Main
    try:
        future = client.request("getBalance", ["test_pubkey"], key="test1")
        client.flush()
        result = future.get()
    except Exception as e:
        logger.info(f"Detected RPC failure on Main: {e}")
    
    # Check that we tried Main first
    main_calls = sum(1 for url in call_count if "helius" in url.lower() or "main" in url.lower())
    if main_calls > 0:
        logger.info("[rpc_failover_smoke] Detected RPC failure on Main...")
    else:
        logger.error("[rpc_failover_smoke] FAILED: Did not try Main first")
        return False
    
    # Check failover to Backup
    backup_calls = sum(1 for url in call_count if "backup" in url.lower())
    if backup_calls > 0 or switch_detected[0]:
        logger.info("[rpc_failover_smoke] Switching to Backup...")
    else:
        logger.error("[rpc_failover_smoke] FAILED: Did not switch to Backup")
        return False
    
    # Verify we got a successful result
    if result is not None:
        logger.info("Failover test: Successfully got result after failover")
        return True
    else:
        logger.error("Failover test: Failed to get result")
        return False


def test_health_score_degradation():
    """Test that health score degrades with errors."""
    logger.info("Testing health score degradation...")
    
    def mock_http(requests):
        raise Exception("HTTP 500")
    
    # Create monitor
    monitor = HealthMonitor(
        health_check_callable=lambda url: {'status': 'ok'},
    )
    
    # Add endpoint
    monitor.add_endpoint("https://failing.rpc")
    
    # Report failures
    for i in range(3):
        monitor.report_failure("https://failing.rpc")
    
    score = monitor.get_score("https://failing.rpc")
    
    if score.errors == 3 and score.score < 50:
        logger.info(f"Health score degraded: {score.score:.1f} after {score.errors} errors")
        return True
    else:
        logger.error(f"Health score not degraded properly: errors={score.errors}, score={score.score}")
        return False


def test_endpoint_selection():
    """Test that best endpoint is selected based on health score."""
    logger.info("Testing endpoint selection...")
    
    def mock_check(url):
        return {'status': 'ok'}
    
    monitor = HealthMonitor(health_check_callable=mock_check)
    failover = FailoverManager(health_monitor=monitor)
    
    # Add endpoints with different priorities
    failover.add_endpoint("https://primary.rpc", priority=0, is_primary=True)
    failover.add_endpoint("https://backup1.rpc", priority=1)
    failover.add_endpoint("https://backup2.rpc", priority=2)
    
    # Get active endpoint (should be primary)
    active = failover.get_active_endpoint()
    
    if active == "https://primary.rpc":
        logger.info("Endpoint selection: Primary selected correctly")
        return True
    else:
        logger.error(f"Endpoint selection: Expected primary, got {active}")
        return False


def test_failover_recovery():
    """Test that endpoint can recover after failures."""
    logger.info("Testing endpoint recovery...")
    
    def mock_check(url):
        return {'status': 'ok'}
    
    monitor = HealthMonitor(health_check_callable=mock_check)
    
    # Add endpoint
    monitor.add_endpoint("https://test.rpc")
    
    # Report some successes
    for i in range(5):
        monitor.report_success("https://test.rpc")
    
    score = monitor.get_score("https://test.rpc")
    
    if score.successes == 5 and score.score > 80:
        logger.info(f"Endpoint recovered: {score.score:.1f} after {score.successes} successes")
        return True
    else:
        logger.error(f"Endpoint recovery failed: successes={score.successes}, score={score.score}")
        return False


def main():
    """Run all tests."""
    tests = [
        ("Failover", test_failover),
        ("Health Score Degradation", test_health_score_degradation),
        ("Endpoint Selection", test_endpoint_selection),
        ("Failover Recovery", test_failover_recovery),
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
        logger.info("[rpc_failover_smoke] OK")
        sys.exit(0)
    else:
        logger.error(f"[rpc_failover_smoke] FAILED ({failed}/{len(results)} tests)")
        sys.exit(1)


if __name__ == '__main__':
    main()
PYEOF

# Run the test
python3 "$TEMP_DIR/test_failover.py"

echo "[rpc_failover_smoke] OK" >&2
