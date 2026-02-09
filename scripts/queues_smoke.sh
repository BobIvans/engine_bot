#!/bin/bash
# scripts/queues_smoke.sh
# PR-D.3 Execution Queues & Rate Limiting - Deterministic Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[queues_smoke] Starting queues smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

from execution.queues import (
    RateLimiter,
    SignalQueue,
    RateLimitedSignalQueue,
    PRIORITY_CRITICAL,
    PRIORITY_EXIT,
    PRIORITY_ENTRY,
)

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [queues] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [queues] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[queues_smoke] Testing RateLimiter...", file=sys.stderr)

# Mock clock for deterministic testing
class MockClock:
    def __init__(self):
        self.time = 0.0
    
    def __call__(self):
        return self.time
    
    def advance(self, seconds):
        self.time += seconds

clock = MockClock()

# Test 1: RateLimiter basic functionality
limiter = RateLimiter(limit=5, window_sec=1.0, clock=clock)
test_case("rate_limiter_init", limiter.limit == 5 and limiter.window_sec == 1.0)

# Test 2: First 5 requests should succeed
for i in range(5):
    result = limiter.can_proceed("test_key")
    test_case(f"rate_limiter_allow_{i}", result == True)
clock.advance(0.1)

# Test 3: 6th request should be rate limited
result = limiter.can_proceed("test_key")
test_case("rate_limiter_block_6th", result == False)

# Test 4: After window, requests should succeed again
clock.advance(1.0)  # Advance past window
result = limiter.can_proceed("test_key")
test_case("rate_limiter_reset_after_window", result == True)

print("[queues_smoke] Testing SignalQueue priority ordering...", file=sys.stderr)

# Test 5: SignalQueue initialization
q = SignalQueue(max_size=100)
test_case("signal_queue_init", q.size() == 0 and q.empty())

# Test 6: Push BUY and SELL signals
buy_signal = {"type": "BUY", "mint": "TokenA", "size_usd": 100}
sell_signal = {"type": "SELL", "mint": "TokenB", "size_usd": 50}

# Push BUY first (lower priority), then SELL (higher priority)
q.push(buy_signal, priority=PRIORITY_ENTRY)
q.push(sell_signal, priority=PRIORITY_EXIT)

# Test 7: SELL should come out first (higher priority = lower number)
first = q.pop()
test_case("priority_sell_before_buy", first["type"] == "SELL", f"got {first}")

# Test 8: BUY should come out second
second = q.pop()
test_case("priority_buy_after_sell", second["type"] == "BUY", f"got {second}")

# Test 9: Queue should be empty
test_case("queue_empty_after_pop", q.empty())

print("[queues_smoke] Testing priority constants...", file=sys.stderr)

# Test 10: Priority ordering
test_case("priority_critical_lowest", PRIORITY_CRITICAL < PRIORITY_EXIT)
test_case("priority_exit_middle", PRIORITY_EXIT < PRIORITY_ENTRY)
test_case("priority_entry_highest", PRIORITY_EXIT < 100)  # Default push priority

print("[queues_smoke] Testing RateLimitedSignalQueue...", file=sys.stderr)

# Test 11: RateLimitedSignalQueue initialization
rlq = RateLimitedSignalQueue(
    max_queue_size=10,
    rate_limit=2,
    rate_window=1.0,
    clock=clock,
)
test_case("rate_limited_queue_init", rlq.size() == 0)

# Test 12: Push signals through rate limiter
for i in range(3):
    result = rlq.push({"id": i}, provider_key="rpc")
    # First 2 should succeed, 3rd should be rate limited
    if i < 2:
        test_case(f"rlq_allow_{i}", result == True)
    else:
        test_case(f"rlq_block_{i}", result == False)

# Test 13: Queue should have 2 items
test_case("rlq_size_2", rlq.size() == 2)

# Test 14: SELL can bypass rate limits
result = rlq.push_bypass({"type": "SELL", "id": 99}, priority=PRIORITY_EXIT)
test_case("rlq_bypass_sell", result == True)

# Test 15: Bypassed SELL should be first
first = rlq.pop()
test_case("rlq_bypass_first", first["type"] == "SELL", f"got {first}")

# Test 16: After window, rate limited pushes should work
clock.advance(1.0)
result = rlq.push({"id": "new"}, provider_key="rpc")
test_case("rlq_allow_after_window", result == True)

# Test 17: Queue full behavior
small_q = SignalQueue(max_size=2)
small_q.push({"id": 1})
small_q.push({"id": 2})
result = small_q.push({"id": 3})
test_case("queue_full_reject", result == False)

# Test 18: get_wait_time calculation
limiter2 = RateLimiter(limit=5, window_sec=1.0, clock=clock)
clock.time = 0.0
for i in range(5):
    limiter2.can_proceed("wait_test")
wait = limiter2.get_wait_time("wait_test")
test_case("wait_time_positive", wait > 0, f"got {wait}")

# Summary
print(f"\n[queues_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[queues_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[queues_smoke] Smoke test completed." >&2
