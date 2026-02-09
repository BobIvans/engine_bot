#!/bin/bash
# Smoke test for Distributed Backtest Harness
# Tests: Parallel execution, grid generation, result aggregation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/parallel"
OUTPUT_FILE="/tmp/optimization_results.json"

echo "[parallel_backtest_smoke] Starting distributed backtest smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_FILE"

# Run parallel backtest
# Grid: tp[0.05, 0.10] * sl[-0.05, -0.02] = 4 combinations
# Workers: 2
echo "[parallel_backtest_smoke] Running parallel backtest with 2 workers..." >&2
python3 -m integration.parallel_backtest \
    --grid "$FIXTURE_DIR/tuning_grid.yaml" \
    --trades "$FIXTURE_DIR/trades_sample.jsonl" \
    --workers 2 \
    --out "$OUTPUT_FILE" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "[parallel_backtest_smoke] FAIL: Output file not created" >&2
    exit 1
fi

# Test 1: Verify correct number of results (4)
echo "[parallel_backtest_smoke] Verifying result count..." >&2
TOTAL_CONFIGS=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['total_configs'])")
SUCCESS_RUNS=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['successful_runs'])")

if [ "$TOTAL_CONFIGS" != "4" ]; then
    echo "[parallel_backtest_smoke] FAIL: Expected 4 configs, got $TOTAL_CONFIGS" >&2
    exit 1
fi

if [ "$SUCCESS_RUNS" != "4" ]; then
    echo "[parallel_backtest_smoke] FAIL: Expected 4 successful runs, got $SUCCESS_RUNS" >&2
    exit 1
fi
echo "[parallel_backtest_smoke] Processed 4 configurations ✓" >&2

# Test 2: Verify best result selection (Sharpe maximization)
# In our simulation: Sharpe = (tp*100) - (abs(sl)*50)
# Configs:
# 1. tp=0.05, sl=-0.05 -> 5 - 2.5 = 2.5
# 2. tp=0.05, sl=-0.02 -> 5 - 1.0 = 4.0
# 3. tp=0.10, sl=-0.05 -> 10 - 2.5 = 7.5
# 4. tp=0.10, sl=-0.02 -> 10 - 1.0 = 9.0  <-- BEST
echo "[parallel_backtest_smoke] Verifying best result selection..." >&2

BEST_SHARPE=$(python3 -c "
import json
data = json.load(open('$OUTPUT_FILE'))
print(data['best_result']['metrics']['sharpe'])
")

BEST_TP=$(python3 -c "
import json
data = json.load(open('$OUTPUT_FILE'))
print(data['best_result']['params']['tp_pct'])
")

BEST_SL=$(python3 -c "
import json
data = json.load(open('$OUTPUT_FILE'))
print(data['best_result']['params']['sl_pct'])
")

if [ "$BEST_SHARPE" != "9.0" ]; then
    echo "[parallel_backtest_smoke] FAIL: Expected best Sharpe 9.0, got $BEST_SHARPE" >&2
    exit 1
fi

if [ "$BEST_TP" != "0.1" ]; then
    echo "[parallel_backtest_smoke] FAIL: Expected best TP 0.1, got $BEST_TP" >&2
    exit 1
fi

if [ "$BEST_SL" != "-0.02" ]; then
    echo "[parallel_backtest_smoke] FAIL: Expected best SL -0.02, got $BEST_SL" >&2
    exit 1
fi
echo "[parallel_backtest_smoke] Best config verified (Sharpe 9.0) ✓" >&2

# Cleanup
rm -f "$OUTPUT_FILE"

echo "[parallel_backtest_smoke] All parallel backtest tests passed!" >&2
echo "[parallel_backtest_smoke] OK ✅"
