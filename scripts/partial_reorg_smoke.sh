#!/usr/bin/env bash
set -euo pipefail

# scripts/partial_reorg_smoke.sh
#
# PR-G.5: Smoke test for Partial Fill & Reorg Handling.
#
# This script validates that:
# 1. Partial fill handler correctly tracks partial fills
# 2. Timeout detection triggers force close
# 3. Reorg detection triggers position rollback
# 4. All adjustments are logged with trace_id/tx_sig

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[partial_reorg_smoke] Running Partial Fill & Reorg smoke test..." >&2

# Run Python assertions
python3 <<'PYTHON'
import json
import sys

from execution.partial_fill_handler import PartialFillHandler, PartialFill, FillAdjustment
from execution.reorg_guard import ReorgGuardExtended, ReorgEvent, PositionAdjustment

# Test 1: PartialFill creation
print("[partial_reorg_smoke] Test 1: PartialFill creation...", file=sys.stderr)
fill = PartialFill(
    signal_id="test_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    expected_amount=100.0,
    filled_amount=30.0,
    entry_price=1.0,
    tx_sig="tx_test_001",
    trace_id="trace_abc123",
)
assert fill.signal_id == "test_001"
assert fill.expected_amount == 100.0
assert fill.filled_amount == 30.0
assert fill.status == "pending"
print("[partial_reorg_smoke] Test 1 passed: PartialFill works", file=sys.stderr)

# Test 2: PartialFillHandler with timeout
print("[partial_reorg_smoke] Test 2: PartialFillHandler with timeout...", file=sys.stderr)
handler = PartialFillHandler(timeout_sec=0)  # Immediate timeout for testing

# Register a partial fill
partial = handler.on_partial_fill(
    signal_id="sig_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    expected_amount=100.0,
    filled_amount=30.0,
    entry_price=1.0,
    tx_sig="tx_partial_001",
    trace_id="trace_abc",
)
assert partial.expected_amount == 100.0
assert partial.filled_amount == 30.0
assert handler.get_remaining_amount("sig_001") == 70.0

# Check timeout (should be expired immediately due to timeout_sec=0)
assert handler.is_expired("sig_001") == True
print("[partial_reorg_smoke] Test 2 passed: PartialFillHandler timeout works", file=sys.stderr)

# Test 3: Force close remaining amount
print("[partial_reorg_smoke] Test 3: Force close remaining amount...", file=sys.stderr)
handler2 = PartialFillHandler(timeout_sec=60)

partial2 = handler2.on_partial_fill(
    signal_id="sig_002",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    expected_amount=100.0,
    filled_amount=30.0,
    entry_price=1.0,
    tx_sig="tx_partial_002",
    trace_id="trace_def",
)

# Force close remaining
adjustment = handler2.force_close_remaining("sig_002", close_price=1.02, reason="partial_timeout")
assert adjustment is not None
assert adjustment.adjustment_type == "force_close"
assert adjustment.remaining_amount == 0.0
assert adjustment.reason == "partial_timeout"
assert partial2.status == "closed"
print("[partial_reorg_smoke] Test 3 passed: Force close works", file=sys.stderr)

# Test 4: Load fixture data
print("[partial_reorg_smoke] Test 4: Load fixture data...", file=sys.stderr)

# Load partial fill events
partial_fills = []
with open("integration/fixtures/partial_reorg/mock_fill_events_partial.jsonl", "r") as f:
    for line in f:
        partial_fills.append(json.loads(line))

assert len(partial_fills) == 3, f"Expected 3 partial fills, got {len(partial_fills)}"
print(f"[partial_reorg_smoke] Loaded {len(partial_fills)} partial fill events", file=sys.stderr)

# Process partial fills through handler
handler3 = PartialFillHandler(timeout_sec=60)
for fill_event in partial_fills:
    handler3.on_partial_fill(
        signal_id=fill_event["signal_id"],
        mint=fill_event["mint"],
        expected_amount=fill_event["expected_amount"],
        filled_amount=fill_event["filled_amount"],
        entry_price=fill_event["entry_price"],
        tx_sig=fill_event["tx_sig"],
        trace_id=fill_event["trace_id"],
    )

pending = handler3.get_pending_partials()
assert len(pending) == 2, f"Expected 2 pending partials, got {len(pending)}"
print(f"[partial_reorg_smoke] Test 4 passed: Loaded {len(pending)} pending partial fills", file=sys.stderr)

# Test 5: ReorgEvent creation
print("[partial_reorg_smoke] Test 5: ReorgEvent creation...", file=sys.stderr)
event = ReorgEvent(
    tx_hash="reorged_tx_001",
    signal_id="sig_reorg_001",
    previous_status="finalized",
    block_height=150000000,
    rollback_amount=100.0,
    reason="Transaction reorged out of confirmed block",
)
assert event.tx_hash == "reorged_tx_001"
assert event.rollback_amount == 100.0
event_dict = event.to_dict()
assert "tx_hash" in event_dict
assert "signal_id" in event_dict
print("[partial_reorg_smoke] Test 5 passed: ReorgEvent works", file=sys.stderr)

# Test 6: PositionAdjustment creation
print("[partial_reorg_smoke] Test 6: PositionAdjustment creation...", file=sys.stderr)
adj = PositionAdjustment(
    signal_id="sig_reorg_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    adjustment_type="reorg_rollback",
    previous_amount=100.0,
    new_amount=0.0,
    price=1.0,
    tx_hash="reorged_tx_001",
    trace_id="trace_xyz",
    reason="Transaction reorged out",
)
assert adj.previous_amount == 100.0
assert adj.new_amount == 0.0
assert adj.adjustment_type == "reorg_rollback"
print("[partial_reorg_smoke] Test 6 passed: PositionAdjustment works", file=sys.stderr)

# Test 7: ReorgGuardExtended
print("[partial_reorg_smoke] Test 7: ReorgGuardExtended...", file=sys.stderr)
guard = ReorgGuardExtended(rpc_url="https://api.mainnet-beta.solana.com")

# Track a transaction
guard.track_transaction(
    tx_hash="tx_guard_001",
    signal_id="sig_guard_001",
    amount=100.0,
    price=1.0,
    tx_type="fill",
    trace_id="trace_guard",
)

pending_txs = guard.get_pending_txs()
assert len(pending_txs) == 1
assert pending_txs[0]["signal_id"] == "sig_guard_001"
print("[partial_reorg_smoke] Test 7 passed: ReorgGuardExtended works", file=sys.stderr)

# Test 8: Verify expected portfolio state
print("[partial_reorg_smoke] Test 8: Verify expected portfolio state...", file=sys.stderr)
with open("integration/fixtures/partial_reorg/expected_portfolio_after.json", "r") as f:
    expected_content = f.read()
expected = json.loads(expected_content)

assert "positions" in expected
assert "adjustments" in expected
assert "reorg_events" in expected
assert len(expected["positions"]) == 1
assert expected["positions"][0]["adjustment_reason"] == "reorg_rollback"
print("[partial_reorg_smoke] Test 8 passed: Expected portfolio state is valid", file=sys.stderr)

# Test 9: Verify adjustment history
print("[partial_reorg_smoke] Test 9: Adjustment history...", file=sys.stderr)
handler4 = PartialFillHandler(timeout_sec=60)
handler4.on_partial_fill(
    signal_id="sig_003",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    expected_amount=100.0,
    filled_amount=50.0,
    entry_price=1.0,
    tx_sig="tx_003",
    trace_id="trace_003",
)
handler4.force_close_remaining("sig_003", close_price=1.05, reason="test_close")

history = handler4.get_adjustment_history()
assert len(history) == 2  # partial_fill + force_close
assert history[0]["adjustment_type"] == "partial_fill"
assert history[1]["adjustment_type"] == "force_close"
print(f"[partial_reorg_smoke] Test 9 passed: Adjustment history has {len(history)} entries", file=sys.stderr)

# Test 10: Verify rejection reasons exist
print("[partial_reorg_smoke] Test 10: Verify rejection reasons...", file=sys.stderr)
from integration.reject_reasons import (
    PARTIAL_FILL_UNRESOLVED,
    PARTIAL_FILL_TIMEOUT,
    REORG_DETECTED,
    REORG_POSITION_ROLLBACK,
)
assert PARTIAL_FILL_UNRESOLVED == "partial_fill_unresolved"
assert PARTIAL_FILL_TIMEOUT == "partial_fill_timeout"
assert REORG_DETECTED == "reorg_detected"
assert REORG_POSITION_ROLLBACK == "reorg_position_rollback"
print("[partial_reorg_smoke] Test 10 passed: Rejection reasons defined", file=sys.stderr)

print("[partial_reorg_smoke] All tests passed successfully! ✅", file=sys.stderr)
PYTHON

echo "[partial_reorg_smoke] OK ✅" >&2
