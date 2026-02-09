#!/usr/bin/env python3
# scripts/coordination_test_disabled.py

import sys

sys.path.insert(0, '.')

from integration.coordination_stage import run_coordination_stage

FIXTURES_DIR = 'integration/fixtures/coordination'

# Run with disabled flag
metrics = run_coordination_stage(
    input_path=f'{FIXTURES_DIR}/trades_clustered.jsonl',
    enabled=False,
    coordination_threshold=0.7,
    window_sec=60.0,
)

if metrics['coordination_score_avg'] == 0.0:
    print('[coordination_smoke] Disabled mode: PASSED (all scores = 0.0)')
else:
    print(f'[coordination_smoke] Disabled mode: FAILED (expected 0.0, got {metrics})')
    sys.exit(1)
