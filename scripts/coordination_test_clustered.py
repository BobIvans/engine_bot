#!/usr/bin/env python3
# scripts/coordination_test_clustered.py

import sys
import json

sys.path.insert(0, '.')

from strategy.coordinated_actions import detect_coordination

FIXTURES_DIR = 'integration/fixtures/coordination'

# Load clustered trades
with open(f'{FIXTURES_DIR}/trades_clustered.jsonl') as f:
    trades = [json.loads(line) for line in f if line.strip()]

# Convert to CoordinationTrade format
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

# Detect coordination
scores = detect_coordination(coord_trades, window_sec=60.0)

print(f"[coordination_smoke] Clustered trades scores: {scores}")

# Validate
values = list(scores.values()) if scores else [0.0]
avg_score = sum(values) / len(values) if values else 0.0
high_count = sum(1 for v in values if v > 0.7)

print(f"[coordination_smoke] Avg score: {avg_score:.3f}, High count: {high_count}")

if avg_score >= 0.7:
    print('[coordination_smoke] Clustered test: PASSED (high coordination detected)')
else:
    print(f'[coordination_smoke] Clustered test: FAILED (avg={avg_score:.3f}, expected >= 0.7)')
    sys.exit(1)
