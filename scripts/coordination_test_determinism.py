#!/usr/bin/env python3
# scripts/coordination_test_determinism.py

import sys
import json

sys.path.insert(0, '.')

from strategy.coordinated_actions import detect_coordination

FIXTURES_DIR = 'integration/fixtures/coordination'

# Load trades once
with open(f'{FIXTURES_DIR}/trades_clustered.jsonl') as f:
    trades = [json.loads(line) for line in f if line.strip()]

coord_trades = [
    {
        "ts_block": t["ts_block"],
        "wallet": t["wallet"],
        "mint": t["mint"],
        "side": t["side"],
        "size": t["size"],
        "price": t["price"],
    }
    for t in trades
]

# Run detection multiple times
results = []
for _ in range(3):
    scores = detect_coordination(coord_trades, window_sec=60.0)
    results.append(json.dumps(scores, sort_keys=True))

if len(set(results)) == 1:
    print('[coordination_smoke] Determinism: PASSED (identical results)')
else:
    print('[coordination_smoke] Determinism: FAILED (results differ)')
    sys.exit(1)
