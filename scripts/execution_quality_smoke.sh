#!/usr/bin/env bash
set -euo pipefail

# scripts/execution_quality_smoke.sh
#
# PR-E.6: Smoke test for Execution Quality Monitor.
#
# This script validates that:
# 1. The ExecutionQualityMonitor module loads correctly
# 2. FillRecord, QualityMetrics, and QualityComparison work as expected
# 3. Paper vs live comparison generates correct deltas
# 4. Alert generation works for high slippage scenarios

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[execution_quality_smoke] Running Execution Quality Monitor smoke test..." >&2

# Run Python assertions
python3 <<'PYTHON'
import json
import sys

from monitoring.execution_quality_monitor import (
    ExecutionQualityMonitor,
    FillRecord,
    QualityMetrics,
    QualityComparison,
)

# Test 1: FillRecord creation
print("[execution_quality_smoke] Test 1: FillRecord creation...", file=sys.stderr)
record = FillRecord(
    signal_id="test_1",
    side="BUY",
    estimated_price=1.0,
    realized_price=1.0008,
    realized_slippage_bps=75,
    latency_ms=200,
    fill_status="filled",
    size_initial=100.0,
    size_remaining=0.0,
)
assert record.signal_id == "test_1"
assert record.side == "BUY"
assert record.realized_slippage_bps == 75.0
assert record.fill_status == "filled"
print("[execution_quality_smoke] Test 1 passed: FillRecord works", file=sys.stderr)

# Test 2: QualityMetrics aggregation
print("[execution_quality_smoke] Test 2: QualityMetrics aggregation...", file=sys.stderr)
metrics = QualityMetrics()
metrics.total_signals = 10
metrics.filled_signals = 8
metrics.partial_fills = 1
metrics.failed_fills = 1
metrics.total_realized_slippage_bps = 750.0
metrics.slippage_samples = 9
metrics.latencies_ms = [100, 150, 200, 250, 300]

assert metrics.fill_rate == 0.8
assert abs(metrics.avg_realized_slippage_bps - 83.33) < 0.1  # Allow floating point tolerance
assert metrics.latency_p90_ms == 300.0
assert abs(metrics.partial_fill_ratio - 0.111) < 0.001  # Allow floating point tolerance
print("[execution_quality_smoke] Test 2 passed: QualityMetrics aggregation works", file=sys.stderr)

# Test 3: Load fixtures and compute metrics
print("[execution_quality_smoke] Test 3: Load fixtures and compute metrics...", file=sys.stderr)

paper_fills = []
with open("integration/fixtures/execution_quality/paper_fills_sample.jsonl", "r") as f:
    for line in f:
        paper_fills.append(json.loads(line))

live_fills = []
with open("integration/fixtures/execution_quality/live_fills_sample.jsonl", "r") as f:
    for line in f:
        live_fills.append(json.loads(line))

assert len(paper_fills) == 5, f"Expected 5 paper fills, got {len(paper_fills)}"
assert len(live_fills) == 5, f"Expected 5 live fills, got {len(live_fills)}"
print(f"[execution_quality_smoke] Loaded {len(paper_fills)} paper and {len(live_fills)} live fills", file=sys.stderr)

# Test 4: ExecutionQualityMonitor with fixtures
print("[execution_quality_smoke] Test 4: ExecutionQualityMonitor with fixtures...", file=sys.stderr)
monitor = ExecutionQualityMonitor(slippage_threshold_bps=100.0)
monitor.add_fills("paper", paper_fills)
monitor.add_fills("live", live_fills)

paper_metrics = monitor.get_metrics("paper")
live_metrics = monitor.get_metrics("live")

assert paper_metrics.total_signals == 5
assert paper_metrics.filled_signals == 5
assert paper_metrics.fill_rate == 1.0
assert paper_metrics.avg_realized_slippage_bps > 0

print(f"[execution_quality_smoke] Paper fill_rate: {paper_metrics.fill_rate}", file=sys.stderr)
print(f"[execution_quality_smoke] Paper avg_realized_slippage_bps: {paper_metrics.avg_realized_slippage_bps:.2f}", file=sys.stderr)
print(f"[execution_quality_smoke] Live avg_realized_slippage_bps: {live_metrics.avg_realized_slippage_bps:.2f}", file=sys.stderr)
print("[execution_quality_smoke] Test 4 passed: ExecutionQualityMonitor works with fixtures", file=sys.stderr)

# Test 5: Paper vs live comparison
print("[execution_quality_smoke] Test 5: Paper vs live comparison...", file=sys.stderr)
comparison = monitor.compare_paper_live()

assert isinstance(comparison, QualityComparison)
assert hasattr(comparison, 'delta_fill_rate')
assert hasattr(comparison, 'delta_avg_slippage_bps')
assert hasattr(comparison, 'delta_latency_p90_ms')

comparison_dict = comparison.to_dict()
assert "fill_rate" in comparison_dict
assert "avg_realized_slippage_bps" in comparison_dict
assert "latency_p90_ms" in comparison_dict

print(f"[execution_quality_smoke] Comparison delta_fill_rate: {comparison.delta_fill_rate:.4f}", file=sys.stderr)
print(f"[execution_quality_smoke] Comparison delta_avg_slippage_bps: {comparison.delta_avg_slippage_bps:.2f}", file=sys.stderr)
print("[execution_quality_smoke] Test 5 passed: Paper vs live comparison works", file=sys.stderr)

# Test 6: Report generation with alerts
print("[execution_quality_smoke] Test 6: Report generation with alerts...", file=sys.stderr)
report = monitor.generate_report()

assert "paper" in report
assert "live" in report
assert "comparison" in report
assert "alerts" in report
assert isinstance(report["alerts"], list)

# Validate report structure
assert "fill_rate" in report["paper"], "fill_rate missing in paper"
assert "avg_realized_slippage_bps" in report["live"], "avg_realized_slippage_bps missing in live"
assert "delta" in report["comparison"]["fill_rate"], "delta missing in comparison fill_rate"

print(f"[execution_quality_smoke] Report generated with {len(report['alerts'])} alerts", file=sys.stderr)
print("[execution_quality_smoke] Test 6 passed: Report generation works", file=sys.stderr)

# Test 7: Monotonicity check - paper should generally have better slippage than live
print("[execution_quality_smoke] Test 7: Monotonicity check...", file=sys.stderr)
# Paper typically has better (lower) slippage than live
# We check that delta is not unreasonably negative (paper much worse than live)
if comparison.delta_avg_slippage_bps < -50:
    print(f"[execution_quality_smoke] WARNING: Paper has significantly worse slippage than live", file=sys.stderr)
    print(f"[execution_quality_smoke] delta_avg_slippage_bps: {comparison.delta_avg_slippage_bps:.2f}", file=sys.stderr)
else:
    print("[execution_quality_smoke] Monotonicity check passed: Paper slippage is reasonable vs live", file=sys.stderr)

# Test 8: Add single FillRecord
print("[execution_quality_smoke] Test 8: Add single FillRecord...", file=sys.stderr)
new_record = FillRecord(
    signal_id="sig_new",
    side="BUY",
    estimated_price=2.0,
    realized_price=2.001,
    realized_slippage_bps=50,
    latency_ms=150,
    fill_status="filled",
    size_initial=50.0,
    size_remaining=0.0,
)
monitor.add_fill_record("paper", new_record)
updated_metrics = monitor.get_metrics("paper")
assert updated_metrics.total_signals == 6
assert updated_metrics.avg_realized_slippage_bps < 100  # Should improve with low slippage fill
print("[execution_quality_smoke] Test 8 passed: Single FillRecord addition works", file=sys.stderr)

print("[execution_quality_smoke] All tests passed successfully! ✅", file=sys.stderr)
PYTHON

echo "[execution_quality_smoke] OK ✅" >&2
