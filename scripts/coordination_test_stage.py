#!/usr/bin/env python3
# scripts/coordination_test_stage.py

import sys
import json

sys.path.insert(0, '.')

from integration.coordination_stage import run_coordination_stage

FIXTURES_DIR = 'integration/fixtures/coordination'

# Run on clustered trades
metrics = run_coordination_stage(
    input_path=f'{FIXTURES_DIR}/trades_clustered.jsonl',
    enabled=True,
    coordination_threshold=0.7,
    window_sec=60.0,
)

print(f"[coordination_smoke] Stage metrics: {json.dumps(metrics, indent=2)}")

avg_score = metrics.get('coordination_score_avg', 0.0)
high_count = metrics.get('coordination_high_count', 0)

if avg_score >= 0.7 and high_count >= 3:
    print('[coordination_smoke] Stage test: PASSED')
else:
    print(f'[coordination_smoke] Stage test: FAILED (avg={avg_score:.3f}, high_count={high_count})')
    sys.exit(1)
