# PR-G.5 Partial Fill & Reorg Handling

**Status:** Implemented  
**Owner:** @ivansbobrovs  
**Created:** 2024-01-15

## Overview

Handles partial fills and micro-forks (reorgs) during order execution, especially in aggressive mode with trailing/partial take. Ensures PortfolioState remains consistent and prevents phantom positions.

## Key Components

### Partial Fill Handler

Tracks partial fills and triggers resolution on timeout:

```python
from execution.partial_fill_handler import PartialFillHandler

handler = PartialFillHandler(timeout_sec=60)

# Register partial fill
handler.on_partial_fill(
    signal_id="sig_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    expected_amount=100.0,
    filled_amount=30.0,
    entry_price=1.0,
    tx_sig="tx_sig_001",
    trace_id="trace_abc",
)

# Check timeout
if handler.is_expired("sig_001"):
    handler.force_close_remaining("sig_001", close_price=1.02)
```

### Reorg Guard (Extended)

Detects reorgs and triggers position rollback:

```python
from execution.reorg_guard import ReorgGuardExtended

guard = ReorgGuardExtended(rpc_url="https://api.mainnet-beta.solana.com")

# Track transaction
guard.track_transaction(
    tx_hash="tx_001",
    signal_id="sig_001",
    amount=100.0,
    price=1.0,
)

# Detect reorg
event = guard.detect_reorg("tx_001")
if event:
    guard.rollback_position(
        signal_id="sig_001",
        mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        previous_amount=100.0,
        new_amount=0.0,
        price=1.0,
        tx_hash="tx_001",
        reason="reorg_rollback",
    )
```

## Reject Reasons

| Reason | Description |
|--------|-------------|
| `partial_fill_unresolved` | Partial fill not resolved within timeout |
| `partial_fill_timeout` | Force close triggered on timeout |
| `reorg_detected` | Reorganization detected |
| `reorg_position_rollback` | Position adjusted due to reorg |

## Integration Points

### With Order Manager

```python
from execution.order_manager import OrderManager
from execution.partial_fill_handler import PartialFillHandler

manager = OrderManager()
handler = PartialFillHandler(timeout_sec=60)

# On partial fill
def on_fill_event(fill_event):
    if fill_event["status"] == "partial":
        handler.on_partial_fill(
            signal_id=fill_event["signal_id"],
            mint=fill_event["mint"],
            expected_amount=fill_event["size"],
            filled_amount=fill_event["filled"],
            entry_price=fill_event["price"],
            tx_sig=fill_event["tx"],
            trace_id=fill_event.get("trace_id"),
        )
```

### With Portfolio State

```python
def on_adjustment(adjustment: PositionAdjustment):
    """Callback to update portfolio state."""
    position = portfolio.get_position(adjustment.signal_id)
    if position:
        position.size_usd = adjustment.new_amount
        position.adjustment_reason = adjustment.reason
        position.adjustment_tx = adjustment.tx_hash
```

## Smoke Test

```bash
./scripts/partial_reorg_smoke.sh
```

Expected output:
```
[partial_reorg_smoke] Running Partial Fill & Reorg smoke test...
[partial_reorg_smoke] Test 1: PartialFill creation... passed
[partial_reorg_smoke] Test 2: PartialFillHandler with timeout... passed
[partial_reorg_smoke] Test 3: Force close remaining amount... passed
...
[partial_reorg_smoke] All tests passed successfully! ✅
[partial_reorg_smoke] OK ✅
```

## GREP Points

```bash
grep -n "PR-G.5" strategy/docs/overlay/PR-G.5.md           # Line 1
grep -n "handle_partial_fill" execution/partial_fill_handler.py  # Multiple matches
grep -n "detect_reorg" execution/reorg_guard.py             # Multiple matches
```

## Related Files

| File | Purpose |
|------|---------|
| [`execution/partial_fill_handler.py`](execution/partial_fill_handler.py) | Partial fill tracking and resolution |
| [`execution/reorg_guard.py`](execution/reorg_guard.py) | Reorg detection and position rollback |
| [`execution/order_manager.py`](execution/order_manager.py) | Position lifecycle management |
| [`integration/reject_reasons.py`](integration/reject_reasons.py) | Reject reason constants |
| [`integration/fixtures/partial_reorg/`](integration/fixtures/partial_reorg/) | Test fixtures |
| [`scripts/partial_reorg_smoke.sh`](scripts/partial_reorg_smoke.sh) | Smoke test |

## Hard Rules

1. **Async handling**: Reorg detection is non-blocking
2. **Position consistency**: Partial fills update PortfolioState.exposure
3. **Timeout resolution**: Force close or cancel on timeout
4. **Trace logging**: All adjustments logged with trace_id/tx_sig
5. **Deterministic tests**: Smoke test runs offline without network calls
