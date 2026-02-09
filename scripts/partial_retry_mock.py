"""scripts/partial_retry_mock.py

Smoke test script for PR-Z.2 Partial Fill Retry.
Simulates a sequence of partial fills and verifies adaptive sizing logic.
"""

import time
import sys
import logging
from decimal import Decimal

# Setup logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("partial_retry")

# Import our modules
try:
    from execution.models import Order
    from execution.partial_retry import PartialFillRetryManager
    from config.runtime_schema import RuntimeConfig
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

def run_test():
    print("Starting Partial Retry Smoke Test...")
    
    # 1. Setup Config
    config = RuntimeConfig(
        partial_retry_enabled=True,
        partial_retry_max_attempts=3,
        partial_retry_size_decay=0.7,
        partial_retry_fee_multiplier=1.5,
        partial_retry_ttl_sec=60
    )
    
    manager = PartialFillRetryManager(config)
    
    # 2. Create Initial Order (Attempt 0)
    # Size 1000 atomic units
    original_size = 1000
    base_fee = 10
    
    order_0 = Order(
        client_id="test_0",
        original_client_id="test_0",
        retry_attempt=0,
        original_size=original_size,
        amount=original_size,
        priority_fee_micro_lamports=base_fee
    )
    
    print(f"Original Order: size={original_size}, fee={base_fee}")
    
    # 3. Simulate Partial Fill 1 (Filled 300)
    # Expected next size: 1000 * 0.7^1 = 700.
    # But budget = 1000 - 300 = 700. Min(700, 700) = 700.
    fill_1 = 300
    print(f"Simulating fill: {fill_1}")
    
    retry_1 = manager.on_partial_fill(order_0, fill_1)
    
    if not retry_1:
        print("FAIL: Expected retry attempt 1")
        sys.exit(1)
        
    print(f"Retry 1: client_id={retry_1.client_id}, size={retry_1.amount}, fee={retry_1.priority_fee_micro_lamports}, cumulative={retry_1.cumulative_filled}")
    
    # Verify properties
    if retry_1.retry_attempt != 1:
        print("FAIL: attempt != 1")
        sys.exit(1)
    if retry_1.amount != 700:
        print(f"FAIL: size {retry_1.amount} != 700")
        sys.exit(1)
    if retry_1.cumulative_filled != 300:
        print(f"FAIL: cumulative {retry_1.cumulative_filled} != 300")
        sys.exit(1)
    if retry_1.priority_fee_micro_lamports != int(base_fee * 1.5):
        print(f"FAIL: fee {retry_1.priority_fee_micro_lamports} != 15")
        sys.exit(1)
        
    # 4. Simulate Partial Fill 2 (Filled 500 of the 700 requested)
    # Cumulative filled = 300 + 500 = 800.
    # Original remaining = 1000 - 800 = 200.
    # Target size = 1000 * 0.7^2 = 1000 * 0.49 = 490.
    # Attempt size = min(490, 200) = 200.
    
    fill_2 = 500
    print(f"Simulating fill 2: {fill_2}")
    
    retry_2 = manager.on_partial_fill(retry_1, fill_2)
    
    if not retry_2:
        print("FAIL: Expected retry attempt 2")
        sys.exit(1)
        
    print(f"Retry 2: client_id={retry_2.client_id}, size={retry_2.amount}, fee={retry_2.priority_fee_micro_lamports}, cumulative={retry_2.cumulative_filled}")
    
    if retry_2.retry_attempt != 2:
        print("FAIL: attempt != 2")
        sys.exit(1)
    if retry_2.amount != 200:
        print(f"FAIL: size {retry_2.amount} != 200 (capped by budget)")
        sys.exit(1)
    if retry_2.cumulative_filled != 800:
        print(f"FAIL: cumulative {retry_2.cumulative_filled} != 800")
        sys.exit(1)
    fee_expected = int(base_fee * (1.5**2)) # 10 * 2.25 = 22.5 -> 22
    if retry_2.priority_fee_micro_lamports != fee_expected:
        print(f"FAIL: fee {retry_2.priority_fee_micro_lamports} != {fee_expected}")
        sys.exit(1)

    # 5. Simulate Full Fill (Filled 200)
    fill_3 = 200
    print(f"Simulating full fill: {fill_3}")
    # This should effectively complete the chain
    # But partial logic checks percentage
    # cumulative = 800 + 200 = 1000. 1000 >= 990.
    
    retry_3 = manager.on_partial_fill(retry_2, fill_3)
    if retry_3 is not None:
        print("FAIL: Expected NO retry (completed)")
        sys.exit(1)
        
    print("Chain completed successfully.")
    
    # 6. Verify Max Attempts
    # Reset
    print("\nTesting Max Attempts...")
    manager = PartialFillRetryManager(config) # New manager
    order_fail = Order(client_id="fail_0", original_client_id="fail_0", retry_attempt=3, original_size=1000, amount=1000, priority_fee_micro_lamports=10)
    # Attempt 3 is max allowed (config=3). Wait, max_attempts=3 means can DO attempt 3? 
    # Logic: if order.retry_attempt >= max_attempts check is BEFORE generating next.
    # If current is 3, next is 4. -> Cancel.
    
    res = manager.on_partial_fill(order_fail, 100)
    if res is not None:
        print("FAIL: Should have rejected retry attempt 4")
        sys.exit(1)
    else:
        print("Max attempts rejected correctly.")

    print("\nSmoke Test PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    run_test()
