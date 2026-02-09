# PR-Z.1 — Master Kill-Switch (Panic Button)

**Status:** Implemented  
**Date:** 2024-01-15  
**Owner:** Operations Team

## Overview

Emergency stop mechanism for immediate strategy shutdown:
- Stops new signal generation
- Cancels pending orders (if possible)
- Closes open positions at market (or hard SL)
- Blocks further actions until manual reset

## Architecture

```
┌─────────────────────┐
│  Flag File          │
│  /tmp/strategy_     │
│  panic.flag         │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     ┌──────────────────────┐
│  ops/panic.py       │────▶│  ops/kill_switch.py │
│  is_panic_active()  │     │  KillSwitch class   │
│  get_panic_reason() │     │  check_panic()      │
└─────────────────────┘     └──────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  paper_pipeline.py  │     │  live_executor.py   │     │  order_manager.py    │
│  check_panic()      │     │  check_panic()      │     │  force_close()       │
└─────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

## Components

### 1. `ops/panic.py`

Core panic detection module:

```python
from ops.panic import is_panic_active, get_panic_reason, PanicShutdown

# Check panic state
if is_panic_active("/tmp/strategy_panic.flag"):
    reason = get_panic_reason()
    logger.critical(f"PANIC: {reason}")

# Or use exception-based check
from ops.panic import require_no_panic
require_no_panic()  # Raises PanicShutdown if active
```

**Functions:**
- `is_panic_active(flag_path) -> bool`: Fast check (< 1ms) with optional caching
- `get_panic_reason(flag_path) -> Optional[str]`: Read reason from flag file
- `create_panic_flag(flag_path, reason)`: Create flag file
- `clear_panic_flag(flag_path) -> bool`: Remove flag file
- `require_no_panic(flag_path)`: Raise PanicShutdown if active

### 2. `ops/kill_switch.py`

Integration layer with execution pipeline:

```python
from ops.kill_switch import KillSwitch, check_panic

# At start of each tick:
check_panic()  # Raises on panic

# Or use KillSwitch class:
ks = KillSwitch(config=kill_config)
ks.check()  # Raises on panic
```

**Classes:**
- `KillSwitchConfig`: Configuration for kill switch behavior
- `KillSwitch`: Main integration class with status and shutdown methods

**Functions:**
- `check_panic(config)`: Check panic state, raise if active
- `force_close_all_positions(executor, order_manager)`: Emergency close
- `cancel_all_pending_orders(executor, order_manager)`: Cancel orders
- `load_kill_switch_config(config_dict)`: Load from dict

## Configuration

```yaml
panic:
  enabled: true
  flag_path: "/tmp/strategy_panic.flag"
  on_panic: "close_all_market"  # "close_all_market" | "hard_stop" | "set_sl"
  cache_ttl_seconds: 0.0  # 0 = no cache for safety
```

## Integration Points

### Paper Pipeline (`integration/paper_pipeline.py`)

```python
from ops.panic import is_panic_active

# At start of main loop:
if is_panic_active():
    logger.critical("PANIC: Stopping paper pipeline")
    return
```

### Live Executor (`execution/live_executor.py`)

```python
from ops.kill_switch import check_panic

# At start of each tick:
async def on_tick(self):
    check_panic()  # Raises PanicShutdown
    # Continue with normal tick processing
```

### Order Manager (`execution/order_manager.py`)

```python
from ops.kill_switch import force_close_all_positions

# On panic:
await force_close_all_positions(executor, self)
```

## Usage

### Activation

```bash
# Via file
echo "Manual panic" > /tmp/strategy_panic.flag

# Via API (if implemented)
curl -X POST http://localhost:8080/panic -d '{"reason": "Manual"}'
```

### Deactivation

```bash
# Remove flag file
rm /tmp/strategy_panic.flag

# Restart strategy to pick up change
```

## Hard Rules

1. **Fast Check**: `is_panic_active()` must complete in < 1ms
2. **Simple Activation**: Flag file is all that's needed
3. **Graceful Shutdown**: Log all actions, close positions safely
4. **Manual Reset**: Only disabled after flag removal + restart
5. **Safe Testing**: Smoke test simulates without real harm

## Testing

Run smoke test:

```bash
bash scripts/kill_switch_smoke.sh
```

Expected output:

```
[overlay_lint] running kill switch smoke...
[kill_switch_smoke] OK
```

## GREP Points

```bash
grep -n "PR-Z.1" strategy/docs/overlay/PR-Z.1.md
grep -n "is_panic_active" ops/panic.py
grep -n "PanicShutdown" ./*.py
grep -n "\[kill_switch_smoke\] OK" scripts/kill_switch_smoke.sh
```

## Related PRs

- **PR-N.3**: Calibrated Inference Adapter (calibration integration)
- **PR-E.5**: Order Manager (position lifecycle)
- **PR-G.1**: Live Executor (transaction execution)

## Safety Considerations

- Never disable kill-switch in production code
- Always log panic activations
- Use market orders for emergency closes (faster than limit)
- Test panic scenarios regularly
- Document all panic activations in incident report
