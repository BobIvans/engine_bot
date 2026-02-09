#!/usr/bin/env python3
# scripts/trailing_dynamic_test.py
# PR-Z.3 Trailing Stop Dynamic Adjustment - Test Runner

import sys
import json
from decimal import Decimal

sys.path.insert(0, '.')

from config.runtime_schema import RuntimeConfig
from execution.market_features import MarketContext
from execution.trailing_adjuster import TrailingAdjuster

FIXTURES_DIR = 'integration/fixtures/trailing'

# Load market context sequence
with open(f'{FIXTURES_DIR}/market_context_sequence.json') as f:
    market_sequence = json.load(f)

# Load expected results
with open(f'{FIXTURES_DIR}/expected_trailing_distances.json') as f:
    expected = json.load(f)

# Create config
config = RuntimeConfig(
    dynamic_trailing_enabled=True,
    trailing_base_distance_bps=150,
    trailing_volatility_multiplier=1.8,
    trailing_volume_multiplier=0.9,
    trailing_max_distance_bps=500,
    trailing_rv_threshold_high=0.08,
    trailing_rv_threshold_low=0.03,
    trailing_volume_confirm_threshold=1.5
)

adjuster = TrailingAdjuster(config)
base_distance = 150

# Test each market context
all_passed = True
for i, market_data in enumerate(market_sequence):
    ctx = MarketContext(
        ts=market_data['ts'],
        mint=market_data['mint'],
        price=Decimal(market_data['price']),
        rv_5m=market_data['rv_5m'],
        rv_15m=market_data['rv_15m'],
        volume_delta_1m=market_data['volume_delta_1m'],
        volume_profile_score=market_data['volume_profile_score'],
        liquidity_usd=market_data.get('liquidity_usd'),
        spread_bps=market_data.get('spread_bps')
    )
    
    expected_dist = expected[i]['expected_distance']
    tolerance = expected[i]['tolerance']
    
    # Compute with logging
    result = adjuster.compute_distance_bps(
        base_distance_bps=base_distance,
        market_ctx=ctx,
        position_side='LONG',
        unrealized_pnl_pct=2.0,  # >0.5% threshold for volume adaptation
        log=True
    )
    
    # Validate
    if abs(result - expected_dist) <= tolerance:
        print(f"[trailing_dynamic_smoke] Test {i}: OK (got {result}, expected {expected_dist} tolerance {tolerance})")
    else:
        print(f"[trailing_dynamic_smoke] Test {i}: FAIL (got {result}, expected {expected_dist} tolerance {tolerance})")
        all_passed = False

# Test 5: Validate outlier rejection
print("[trailing_dynamic_smoke] Testing outlier rejection (RV > 50%)...")
ctx_outlier = MarketContext(
    ts=1700000000.0,
    mint='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    price=Decimal('1.00'),
    rv_5m=0.60,  # Extreme outlier
    rv_15m=0.50,
    volume_delta_1m=0.5,
    volume_profile_score=0.7
)

result_outlier = adjuster.compute_distance_bps(
    base_distance_bps=150,
    market_ctx=ctx_outlier,
    position_side='LONG',
    unrealized_pnl_pct=2.0,
    log=True
)

if result_outlier == 150:
    print('[trailing_dynamic_smoke] Outlier rejection: OK (returned base distance)')
else:
    print(f'[trailing_dynamic_smoke] Outlier rejection: FAIL (got {result_outlier})')
    all_passed = False

# Test 6: Validate hard cap
print("[trailing_dynamic_smoke] Testing hard cap (RV=0.3, volume=-1.9)...")
ctx_hardcap = MarketContext(
    ts=1700000000.0,
    mint='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    price=Decimal('1.00'),
    rv_5m=0.30,  # High volatility
    rv_15m=0.25,
    volume_delta_1m=-0.5,
    volume_profile_score=0.2
)

result_hardcap = adjuster.compute_distance_bps(
    base_distance_bps=150,
    market_ctx=ctx_hardcap,
    position_side='LONG',
    unrealized_pnl_pct=2.0,
    log=True
)

if result_hardcap <= 500:
    print(f'[trailing_dynamic_smoke] Hard cap: OK (result {result_hardcap} <= 500)')
else:
    print(f'[trailing_dynamic_smoke] Hard cap: FAIL (got {result_hardcap})')
    all_passed = False

# Test 7: Determinism check (same input = same output)
print("[trailing_dynamic_smoke] Testing determinism (idempotency)...")
ctx_deterministic = MarketContext(
    ts=1700000000.0,
    mint='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    price=Decimal('1.00'),
    rv_5m=0.12,
    rv_15m=0.10,
    volume_delta_1m=0.5,
    volume_profile_score=0.7
)

results = []
for _ in range(3):
    adjuster_new = TrailingAdjuster(config)
    result_det = adjuster_new.compute_distance_bps(150, ctx_deterministic, 'LONG', 2.0, log=False)
    results.append(result_det)

if len(set(results)) == 1:
    print(f'[trailing_dynamic_smoke] Determinism: OK (all 3 runs = {results[0]})')
else:
    print(f'[trailing_dynamic_smoke] Determinism: FAIL (results differ: {results})')
    all_passed = False

if not all_passed:
    sys.exit(1)

print('[trailing_dynamic_smoke] All tests passed!')
