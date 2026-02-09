# PR-K.3 Honeypot Safety Gate

**Status:** Implemented  
**Owner:** @ivansbobrovs  
**Created:** 2024-01-15

## Overview

Integrates honeypot-flag checking into hard gates to reject scam/honeypot tokens before probability and EV calculation. Uses `honeypot_filter.is_honeypot_safe()` to determine token safety.

## Key Components

### Honeypot Gate Function

```python
from integration.gates import passes_honeypot_gate, apply_gates

# Check if token passes honeypot gate
passed, reason = passes_honeypot_gate(snapshot, config)

if not passed:
    # Token rejected
    print(f"Rejected: {reason}")
```

### Configuration

```yaml
security:
  require_honeypot_safe: true  # Enable honeypot check
```

## Usage

### With apply_gates (full gate suite)

```python
from integration.gates import apply_gates

decision = apply_gates(config, trade, snapshot)

if not decision.passed:
    print(f"Rejected: {decision.reasons}")
else:
    # Proceed with signal
    pass
```

### Standalone honeypot check

```python
from integration.gates import passes_honeypot_gate

passed, reason = passes_honeypot_gate(snapshot, config)

if passed:
    print("Token is honeypot-safe")
else:
    print(f"Token rejected: {reason}")
```

## Reject Reasons

| Reason | Description |
|--------|-------------|
| `honeypot_detected` | Token flagged as honeypot |
| `honeypot_check_skipped` | Honeypot check disabled in config |

## Integration Points

### TokenSnapshot

The `TokenSnapshot` dataclass includes an `extra` field for security and simulation data:

```python
@dataclass
class TokenSnapshot:
    mint: str
    liquidity_usd: Optional[float]
    extra: Optional[Dict[str, Any]]  # Contains security.simulation data
```

### Honeypot Filter

```python
from strategy.honeypot_filter import is_honeypot_safe

is_safe = is_honeypot_safe(
    mint=token_mint,
    snapshot_extra=snapshot.extra,
    simulation_success=True,
    buy_tax_bps=0,
    sell_tax_bps=0,
    is_freezable=False,
)
```

## Smoke Test

```bash
./scripts/honeypot_gate_smoke.sh
```

Expected output:
```
[honeypot_gate_smoke] Running Honeypot Safety Gate smoke test...
[honeypot_gate_smoke] Test 1: Check HONEYPOT_DETECTED in reject_reasons... passed
[honeypot_gate_smoke] Test 2: Safe token with require_honeypot_safe=true... passed
[honeypot_gate_smoke] Test 3: Honeypot token with require_honeypot_safe=true... passed
[honeypot_gate_smoke] Test 4: Safe token with require_honeypot_safe=false... passed
[honeypot_gate_smoke] Test 5: Honeypot token with require_honeypot_safe=false... passed
...
[honeypot_gate_smoke] All tests passed successfully! ✅
[honeypot_gate_smoke] OK ✅
```

## GREP Points

```bash
grep -n "PR-K.3" strategy/docs/overlay/PR-K.3.md           # Line 1
grep -n "honeypot_detected" integration/reject_reasons.py  # Line 30
grep -n "passes_honeypot_gate" integration/gates.py        # Line 227
grep -n "require_honeypot_safe" integration/gates.py        # Line 240
grep -n "\[honeypot_gate_smoke\] OK" scripts/honeypot_gate_smoke.sh  # Line 125
```

## Related Files

| File | Purpose |
|------|---------|
| [`integration/gates.py`](integration/gates.py) | Hard gates implementation with honeypot gate |
| [`strategy/honeypot_filter.py`](strategy/honeypot_filter.py) | Honeypot detection logic |
| [`integration/token_snapshot_store.py`](integration/token_snapshot_store.py) | Token snapshot cache |
| [`integration/reject_reasons.py`](integration/reject_reasons.py) | Reject reason constants |
| [`integration/fixtures/honeypot_gate/`](integration/fixtures/honeypot_gate/) | Test fixtures |
| [`scripts/honeypot_gate_smoke.sh`](scripts/honeypot_gate_smoke.sh) | Smoke test |

## Hard Rules

1. **Configurable**: Check only runs when `require_honeypot_safe == true`
2. **No snapshot handling**: Missing snapshot is not an automatic rejection for honeypot
3. **Canonical reasons**: Uses `honeypot_detected` from reject_reasons.py
4. **No network calls**: All checks are pure functions
5. **Deterministic**: Fully testable offline
