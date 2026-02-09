#!/bin/bash
# Smoke test for Polymarket-Augmented Features (PR-ML.1)
# Tests: schema validation, feature computation, aggregation logic

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Polymarket Features Smoke Test ===" >&2
echo "" >&2

# Test 1: Pure functions import and validation
echo "[1/4] Testing pure function imports..." >&2
python3 -c "
from analysis.polymarket_features import (
    PolymarketSnapshot,
    PolymarketTokenMapping,
    EventRiskTimeline,
    compute_pmkt_bullish_score,
    compute_pmkt_event_risk,
    compute_pmkt_volatility_zscore,
    compute_pmkt_volume_spike_factor,
    compute_all_pmkt_features,
)

# Test bullish score computation
bullish_snapshots = [
    PolymarketSnapshot(
        ts=1704067200000 + i * 3600000,
        market_id='market_1',
        question='Test?',
        p_yes=0.6 + i * 0.04,
        p_no=0.4 - i * 0.04,
        volume_usd=10000 + i * 5000,
        event_date=1706755200000,
        category_tags=['test'],
    )
    for i in range(6)
]

mapping = PolymarketTokenMapping(
    market_id='market_1',
    token_mint='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    token_symbol='WIF',
    relevance_score=0.9,
    mapping_type='thematic',
    matched_keywords=['test'],
)

score = compute_pmkt_bullish_score(bullish_snapshots, mapping)
assert -1.0 <= score <= 1.0, f'Bullish score out of range: {score}'
print('  ✓ compute_pmkt_bullish_score: OK')

# Test event risk
event_risk = EventRiskTimeline(
    market_id='market_1',
    high_event_risk=True,
    days_to_resolution=2,
    risk_factors=['test'],
)
risk = compute_pmkt_event_risk(event_risk)
assert risk == 1.0, f'Expected 1.0, got {risk}'
print('  ✓ compute_pmkt_event_risk: OK')

# Test volatility zscore
vol_zscore = compute_pmkt_volatility_zscore(bullish_snapshots)
assert -5.0 <= vol_zscore <= 5.0, f'Volatility zscore out of range: {vol_zscore}'
print('  ✓ compute_pmkt_volatility_zscore: OK')

# Test volume spike
spike = compute_pmkt_volume_spike_factor(bullish_snapshots)
assert 0.0 <= spike <= 10.0, f'Volume spike out of range: {spike}'
print('  ✓ compute_pmkt_volume_spike_factor: OK')

print('  ✓ All pure functions validated')
"
echo "" >&2

# Test 2: Feature keys V5
echo "[2/4] Testing FEATURE_KEYS_V5..." >&2
python3 -c "
from features.trade_features import FEATURE_KEYS_V5

expected_keys = [
    'f_trade_size_usd', 'f_price', 'f_side_is_buy',
    'f_token_liquidity_usd', 'f_token_spread_bps',
    'f_wallet_roi_30d_pct', 'f_wallet_winrate_30d', 'f_wallet_trades_30d',
    'f_token_vol_30s', 'f_token_impulse_5m', 'f_smart_money_share',
    'f_smart_money_count_60s',
    'f_wallet_exit_prob_60s',
    'f_pmkt_bullish_score', 'f_pmkt_event_risk',
    'f_pmkt_volatility_zscore', 'f_pmkt_volume_spike_factor',
]

assert FEATURE_KEYS_V5 == expected_keys, 'FEATURE_KEYS_V5 mismatch'
print(f'  ✓ FEATURE_KEYS_V5 contains {len(FEATURE_KEYS_V5)} keys')
"
echo "" >&2

# Test 3: Fixture loading
echo "[3/4] Testing fixture loading..." >&2
python3 -c "
import json
from pathlib import Path

# Load snapshots fixture
snapshots_path = Path('$PROJECT_ROOT/integration/fixtures/ml/polymarket_snapshots_features_sample.parquet')
assert snapshots_path.exists(), 'Snapshots fixture not found'
print('  ✓ Snapshots fixture exists')

# Load mapping fixture
mapping_path = Path('$PROJECT_ROOT/integration/fixtures/ml/polymarket_token_mapping_features_sample.parquet')
assert mapping_path.exists(), 'Mapping fixture not found'
print('  ✓ Mapping fixture exists')

# Parse fixtures (JSON format for test)
with open(str(snapshots_path).replace('.parquet', ''), 'r') as f:
    data = json.load(f)
assert 'markets' in data, 'Invalid snapshots fixture format'
print('  ✓ Snapshots fixture parsed')

with open(str(mapping_path).replace('.parquet', ''), 'r') as f:
    data = json.load(f)
assert 'mappings' in data, 'Invalid mapping fixture format'
print('  ✓ Mapping fixture parsed')
"
echo "" >&2

# Test 4: Expected values validation
echo "[4/4] Testing expected values on fixtures..." >&2
python3 -c "
import json
from pathlib import Path
from analysis.polymarket_features import (
    PolymarketSnapshot,
    PolymarketTokenMapping,
    compute_pmkt_bullish_score,
)

# Load and process bullish market data
snapshots_path = Path('$PROJECT_ROOT/integration/fixtures/ml/polymarket_snapshots_features_sample.parquet')
mapping_path = Path('$PROJECT_ROOT/integration/fixtures/ml/polymarket_token_mapping_features_sample.parquet')

with open(str(snapshots_path).replace('.parquet', ''), 'r') as f:
    snapshots_data = json.load(f)

with open(str(mapping_path).replace('.parquet', ''), 'r') as f:
    mapping_data = json.load(f)

# Build snapshots for bullish market
bullish_market = snapshots_data['markets']['market_bullish']
market_id = bullish_market['market_id']
snapshots = [
    PolymarketSnapshot(
        ts=s['ts'],
        market_id=market_id,
        question=bullish_market['question'],
        p_yes=s['p_yes'],
        p_no=s['p_no'],
        volume_usd=s['volume_usd'],
        event_date=1706755200000,
        category_tags=['crypto'],
    )
    for s in bullish_market['snapshots']
]

# Find WIF mapping
wif_mapping = None
for m in mapping_data['mappings']:
    if m['token_symbol'] == 'WIF':
        for mapping in m['mappings']:
            if mapping['market_id'] == market_id:
                wif_mapping = PolymarketTokenMapping(
                    market_id=mapping['market_id'],
                    token_mint=m['token_mint'],
                    token_symbol=m['token_symbol'],
                    relevance_score=mapping['relevance_score'],
                    mapping_type=mapping['mapping_type'],
                    matched_keywords=mapping['matched_keywords'],
                )
                break

assert wif_mapping is not None, 'WIF mapping not found'

# Compute bullish score
score = compute_pmkt_bullish_score(snapshots, wif_mapping)
assert score > 0, f'Expected positive bullish score for bullish market, got {score}'
print(f'  ✓ WIF bullish score: {score:.2f} (expected > 0)')

# Validate ranges
assert -1.0 <= score <= 1.0, f'Score out of range: {score}'
print('  ✓ Score within [-1.0, +1.0] range')
"
echo "" >&2

echo "[polymarket_features_smoke] OK" >&2
echo "" >&2
echo "=== All Polymarket feature tests passed! ===" >&2
