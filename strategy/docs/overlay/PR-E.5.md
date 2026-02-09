# PR-E.5 Mode-Based Order Manager (TTL & Bracket Orders)

**Status:** Implemented  
**Owner:** @ivansbobrovs  
**Created:** 2024-01-15

## Overview

Manages position lifecycle after entry with TTL, TP, and SL monitoring. Accepts parameters from Signal, tracks TTL from fill moment, and triggers closes on TP/SL/TTL expiration.

## Position States

```
ACTIVE  → EXPIRED (TTL)
ACTIVE  → CLOSED  (TP)
ACTIVE  → CLOSED  (SL)
ACTIVE  → PARTIAL (partial fill)
PARTIAL → CLOSED  (remaining fill/TTL/TP/SL)
```

## Key Components

### Position Dataclass

```python
from execution.position_state import Position, create_position_from_signal

position = create_position_from_signal(
    signal_id="sig_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    entry_price=100.0,
    size_usd=100.0,
    ttl_sec=3600,
    tp_pct=0.05,  # 5% take-profit
    sl_pct=0.03,  # 3% stop-loss
)
```

### OrderManager

```python
from execution.order_manager import OrderManager

manager = OrderManager(dry_run=False)

# Register position after fill
position = manager.on_fill(
    signal_id="sig_001",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    entry_price=100.0,
    size_usd=100.0,
    entry_ts=datetime.now(timezone.utc),
    ttl_seconds=3600,
    tp_price=105.0,
    sl_price=97.0,
)

# Force close
action = manager.force_close("sig_001", "ttl_expired", price=100.0)
```

## Hard Rules

1. **TTL from fill**: TTL counts from fill moment, not signal
2. **Idempotent closes**: Multiple close calls don't change state
3. **Dry-run mode**: Virtual state changes only
4. **Event-driven**: No blocking sleeps, uses on_tick pattern

## State Transitions

### TTL Expiration
```
TTL expired → force_close(signal_id, "ttl_expired", price)
```

### TP Hit
```
Price >= tp_price (BUY) or Price <= tp_price (SELL)
→ force_close(signal_id, "tp_hit", price)
```

### SL Hit
```
Price <= sl_price (BUY) or Price >= sl_price (SELL)
→ force_close(signal_id, "sl_hit", price)
```

## Reject Reasons

| Reason | Description |
|--------|-------------|
| `ttl_expired` | TTL reached without close |
| `tp_hit` | Take-profit price hit |
| `sl_hit` | Stop-loss price hit |
| `manual_close` | Manual force close |

## Smoke Test

```bash
./scripts/order_manager_smoke.sh
```

Expected output:
```
[order_manager_smoke] Running Order Manager smoke test...
[order_manager_smoke] Test 1: Check reject reasons... passed
[order_manager_smoke] Test 2: Create position from signal... passed
[order_manager_smoke] Test 3: TTL expiration check... passed
[order_manager_smoke] Test 4: TP hit check... passed
[order_manager_smoke] Test 5: SL hit check... passed
[order_manager_smoke] Test 6: SELL side checks... passed
[order_manager_smoke] Test 7: OrderManager registration... passed
[order_manager_smoke] Test 8: Force close by TTL... passed
[order_manager_smoke] Test 9: Force close by TP... passed
[order_manager_smoke] Test 10: Force close by SL... passed
[order_manager_smoke] Test 11: Idempotent close... passed
[order_manager_smoke] All tests passed successfully! ✅
[order_manager_smoke] OK ✅
```

## GREP Points

```bash
grep -n "PR-E.5" strategy/docs/overlay/PR-E.5.md           # Line 1
grep -n "OrderManager" execution/order_manager.py           # Multiple matches
grep -n "ttl_expires_at" execution/position_state.py         # Line 33
grep -n "ttl_expired" integration/reject_reasons.py          # Line 61
grep -n "\[order_manager_smoke\] OK" scripts/order_manager_smoke.sh  # Line 170
```

## Related Files

| File | Purpose |
|------|---------|
| [`execution/order_manager.py`](execution/order_manager.py) | Order manager implementation |
| [`execution/position_state.py`](execution/position_state.py) | Position state and transitions |
| [`execution/order_state_machine.py`](execution/order_state_machine.py) | State machine definitions |
| [`integration/reject_reasons.py`](integration/reject_reasons.py) | Reject reason constants |
| [`integration/fixtures/order_manager/`](integration/fixtures/order_manager/) | Test fixtures |
| [`scripts/order_manager_smoke.sh`](scripts/order_manager_smoke.sh) | Smoke test |
