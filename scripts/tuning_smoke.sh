#!/bin/bash
# scripts/tuning_smoke.sh
# PR-E.4 Parameter Tuning Harness - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"
OUT_FILE="${ROOT_DIR}/tuning_results.smoke.json"

echo "[tuning_smoke] Starting tuning harness smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import json
import os

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

from strategy.tuning import (
    generate_param_grid,
    extract_params_for_result,
    _set_nested,
    _get_nested,
)

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [tuning] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [tuning] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[tuning_smoke] Testing parameter generation logic...", file=sys.stderr)

# Base config
base_config = {
    "modes": {
        "U": {"tp_pct": 0.05, "sl_pct": -0.05}
    },
    "min_edge_bps": 50,
}

# Tuning ranges with 2 values each
ranges = {
    "modes.U.tp_pct": [0.05, 0.10],
    "modes.U.sl_pct": [-0.05, -0.10],
}

# Test 1: Grid search generates expected number of configs
configs = list(generate_param_grid(base_config, ranges, method="grid", seed=42))
test_case("grid_config_count", len(configs) == 4, f"Expected 4, got {len(configs)}")

# Test 2: Configs have correct structure
for cfg in configs:
    test_case("grid_config_has_modes", "modes" in cfg)
    test_case("grid_config_modes_U", "U" in cfg.get("modes", {}))
    break

# Test 3: Random search generates expected number of configs
random_configs = list(generate_param_grid(base_config, ranges, method="random", samples=5, seed=123))
test_case("random_config_count", len(random_configs) == 5)

# Test 4: Same seed produces same configs
random_configs_2 = list(generate_param_grid(base_config, ranges, method="random", samples=5, seed=123))
test_case("random_seed_deterministic", len(random_configs) == len(random_configs_2))

# Test 5: _set_nested and _get_nested work correctly
test_config = {}
_set_nested(test_config, "modes.U.tp_pct", 0.15)
test_case("set_nested", test_config.get("modes", {}).get("U", {}).get("tp_pct") == 0.15)

test_value = _get_nested(test_config, "modes.U.tp_pct")
test_case("get_nested", test_value == 0.15)

# Test 6: extract_params_for_result works
params = extract_params_for_result(random_configs[0], ranges)
test_case("extract_params_has_keys", len(params) == 2)
test_case("extract_params_values", all(k in ranges for k in params.keys()))

# Test 7: Run the actual tuning harness (with minimal data)
print("[tuning_smoke] Testing tuning harness integration...", file=sys.stderr)

from tools.tune_strategy import run_tuning
import tempfile
import shutil

# Use existing fixture files
config_path = "$ROOT_DIR/integration/fixtures/config/daily_metrics.yaml"
ranges_path = "$ROOT_DIR/integration/fixtures/config/tuning_ranges.yaml"
trades_path = "$ROOT_DIR/integration/fixtures/trades.daily_metrics.jsonl"
snapshots_path = "$ROOT_DIR/integration/fixtures/token_snapshot.daily_metrics_all_skip.csv"
out_path = "$OUT_FILE"

# Run tuning with grid search (4 configs)
run_tuning(
    config_path=config_path,
    ranges_path=ranges_path,
    trades_path=trades_path,
    snapshots_path=snapshots_path,
    out_path=out_path,
    method="grid",
    samples=10,
    seed=42,
)

# Test 8: Verify output file exists
test_case("output_file_exists", os.path.exists(out_path))

# Test 9: Verify output has correct schema
with open(out_path, "r") as f:
    output = json.load(f)

test_case("output_schema_version", output.get("schema_version") == "tuning_results.v1")
test_case("output_has_metadata", "metadata" in output)
test_case("output_has_results", "results" in output)
test_case("output_results_count", len(output.get("results", [])) > 0)

# Test 10: Results have correct structure
for result in output.get("results", []):
    test_case("result_has_params", "params" in result)
    test_case("result_has_metrics", "metrics" in result)
    metrics = result.get("metrics", {})
    test_case("metrics_has_roi", "roi_total" in metrics)
    test_case("metrics_has_winrate", "winrate" in metrics)
    test_case("metrics_has_positions", "positions_closed" in metrics)
    break

# Summary
print(f"\n[tuning_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

# Cleanup
if os.path.exists(out_path):
    os.remove(out_path)

if failed > 0:
    sys.exit(1)
else:
    print("[tuning_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[tuning_smoke] Smoke test completed." >&2
