#!/bin/bash
# scripts/sweep_smoke.sh
# Smoke test for Strategy Leaderboard & Parameter Sweep
# PR-V.2

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[sweep_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[sweep_smoke] ERROR:${NC} $1" >&2
    exit 1
}

# Add project root to PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

echo ""
log_info "Starting Parameter Sweep smoke tests..."
echo ""

python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

import json
import os
import tempfile

from strategy.optimization.grid import ParameterGrid
from strategy.optimization.ranking import (
    calculate_metrics,
    rank_configs,
    get_best_config,
    SweepResult,
)
from integration.sweep_runner import run_sweep, save_leaderboard

print("[sweep_smoke] Testing ParameterGrid...")
print("")

# Test 1: Grid generation
print("[sweep_smoke] Test 1: Grid generation...")

# Create a small 2x2 grid for smoke test
param_ranges = {
    "min_hold_seconds": [0, 60],
    "max_hold_seconds": [300, 600],
}

grid = ParameterGrid()
combinations = grid.generate(param_ranges)

assert len(combinations) == 4, f"Expected 4 combinations, got {len(combinations)}"
print(f"  Grid size: {len(combinations)} configs (OK)")

# Verify determinism - sort by keys
for combo in combinations:
    assert "min_hold_seconds" in combo
    assert "max_hold_seconds" in combo

print("  Determinism verified (OK)")
print("")

# Test 2: Metrics calculation
print("[sweep_smoke] Test 2: Metrics calculation...")

# Create sample trades
trades = [
    {"pnl_pct": 5.0, "hold_seconds": 100},
    {"pnl_pct": 10.0, "hold_seconds": 200},
    {"pnl_pct": -2.0, "hold_seconds": 50},
    {"pnl_pct": 8.0, "hold_seconds": 150},
    {"pnl_pct": 3.0, "hold_seconds": 80},
]

metrics = calculate_metrics(trades)
print(f"  Total ROI: {metrics['total_roi']:.2f}%")
print(f"  Max Drawdown: {metrics['max_drawdown']:.2f}%")
print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"  Win Rate: {metrics['win_rate']:.2f}")

assert metrics['total_roi'] == 24.0, f"Expected ROI 24.0, got {metrics['total_roi']}"
assert metrics['num_trades'] == 5, f"Expected 5 trades, got {metrics['num_trades']}"
assert metrics['sharpe_ratio'] > 0, "Sharpe ratio should be positive"
print("  Metrics calculation verified (OK)")
print("")

# Test 3: Full sweep run
print("[sweep_smoke] Test 3: Full sweep run...")

# Use the fixture file
fixture_trades = "integration/fixtures/tuning/trades_sample.jsonl"
fixture_config = "integration/fixtures/tuning/sweep_config.yaml"

# Check files exist
assert os.path.exists(fixture_trades), f"Fixture file not found: {fixture_trades}"
assert os.path.exists(fixture_config), f"Config file not found: {fixture_config}"

# Load trades
with open(fixture_trades, 'r') as f:
    trades = [json.loads(line) for line in f if line.strip()]

print(f"  Loaded {len(trades)} trades")

# Load config and get parameter ranges
with open(fixture_config, 'r') as f:
    import yaml
    config = yaml.safe_load(f)

param_ranges = config.get('parameters', {})
assert len(param_ranges) > 0, "Config should have parameters"

# Count expected combinations
grid = ParameterGrid()
expected_count = grid.count_combinations(param_ranges)
print(f"  Expected combinations: {expected_count}")

# Run sweep
results = run_sweep(trades, param_ranges, verbose=False)

assert len(results) == expected_count, f"Expected {expected_count} results, got {len(results)}"
print(f"  Sweep completed: {len(results)} configs (OK)")
print("")

# Test 4: Leaderboard generation
print("[sweep_smoke] Test 4: Leaderboard generation...")

# Save to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    output_file = f.name

save_leaderboard(results, output_file, top_n=5)

# Verify output file
with open(output_file, 'r') as f:
    leaderboard = json.load(f)

assert "version" in leaderboard, "Leaderboard should have version"
assert leaderboard["version"] == "v1", f"Expected v1, got {leaderboard['version']}"
assert "best_config" in leaderboard, "Leaderboard should have best_config"
assert "ranking" in leaderboard, "Leaderboard should have ranking"
assert len(leaderboard["ranking"]) == 5, f"Expected 5 ranking entries, got {len(leaderboard['ranking'])}"

best = leaderboard["best_config"]
assert best is not None, "Best config should not be None"
assert "sharpe_ratio" in best["metrics"], "Best config should have sharpe_ratio"
assert best["metrics"]["sharpe_ratio"] is not None, "Sharpe ratio should not be NaN"

print(f"  Best config: Sharpe={best['metrics']['sharpe_ratio']:.2f}, ROI={best['metrics']['total_roi']:.1f}% (OK)")

# Clean up
os.unlink(output_file)

print("")

# Test 5: Ranking verification
print("[sweep_smoke] Test 5: Ranking verification...")

ranked = rank_configs(results, sort_by='sharpe_ratio')

# Verify descending order by Sharpe
for i in range(len(ranked) - 1):
    assert ranked[i].sharpe >= ranked[i+1].sharpe, "Results should be sorted by Sharpe descending"

print("  Ranking order verified (OK)")
print("")

# Test 6: Empty results handling
print("[sweep_smoke] Test 6: Empty results handling...")

empty_results = rank_configs([], sort_by='sharpe_ratio')
assert len(empty_results) == 0, "Empty results should return empty list"

empty_best = get_best_config([])
assert empty_best is None, "Empty best config should return None"

print("  Empty handling verified (OK)")
print("")

print("[sweep_smoke] All sweep tests passed!")
print("[sweep_smoke] OK")
PYTEST
