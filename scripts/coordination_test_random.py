#!/usr/bin/env python3
# scripts/coordination_test_random.py

import sys
import json

sys.path.insert(0, '.')

from strategy.coordinated_actions import detect_coordination

FIXTURES_DIR = 'integration/fixtures/coordination'

# Load random trades
with open(f'{FIXTURES_DIR}/trades_random.jsonl') as f:
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

print(f"[coordination_smoke] Random trades scores: {scores}")

# Validate
values = list(scores.values()) if scores else [0.0]
avg_score = sum(values) / len(values) if values else 0.0

print(f"[coordination_smoke] Avg score: {avg_score:.3f}")

if avg_score <= 0.3:
    print('[coordination_smoke] Random test: PASSED (low coordination detected)')
else:
    print(f'[coordination_smoke] Random test: FAILED (avg={avg_score:.3f}, expected <= 0.3)')
    sys.exit(1)
