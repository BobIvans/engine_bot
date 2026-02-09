# PR-X.1 — State Reconciler (Watchdog)

**Status:** Implemented  
**Date:** 2024-01-15  
**Author:** Strategy Team

## Overview

Background watchdog mechanism that periodically reconciles on-chain vs local balance (PortfolioState).  
Detects discrepancies caused by:
- Missed transactions
- Reorg effects
- RPC inconsistencies

Creates adjustment records and sends alerts when thresholds are exceeded.

## Architecture

### Components

1. **`monitoring/state_reconciler.py`** - Core reconciliation logic
   - `StateReconciler` - Main class for balance checking
   - `BalanceAdjustment` - Adjustment record dataclass
   - `ReconcilerConfig` - Configuration dataclass
   - `AdjustmentReason` - Enum for discrepancy reasons

2. **`monitoring/state_reconciler_worker.py`** - Background daemon
   - `StateReconcilerWorker` - Async worker with shutdown handling
   - `run_reconciler()` - Convenience function

3. **`monitoring/alerts.py`** - Alert composition
   - `compose_balance_discrepancy_alert()` - Format alert message
   - `ALERT_BALANCE_DISCREPANCY` - Alert type constant

## Adjustment Record Structure

```python
@dataclass
class BalanceAdjustment:
    timestamp: datetime
    local_balance_lamports_before: int      # Local state before adjustment
    onchain_balance_lamports: int          # Actual on-chain balance
    delta_lamports: int                    # Difference (onchain - local)
    reason: str                             # "missed_tx", "reorg", "rpc_inconsistency"
    tx_signatures: List[str]                # Associated transactions
    adjusted: bool                          # Was adjustment applied?
```

### Reasons

| Reason | Description |
|--------|-------------|
| `missed_tx` | On-chain change not in local state |
| `reorg` | Block reorganization reversed local state |
| `rpc_inconsistency` | RPC returned stale data |
| `unknown` | Unable to determine cause |

## Configuration

### Config Structure (config/monitoring.yaml)

```yaml
state_reconciler:
  enabled: true                    # Enable/disable reconciler
  interval_seconds: 300            # Check every 5 minutes
  warning_threshold_lamports: 5000000      # ~0.005 SOL
  critical_threshold_lamports: 50000000    # ~0.05 SOL
  max_delta_without_alert_lamports: 1000000  # Ignore < 0.001 SOL
```

## Usage Example

```python
from monitoring.state_reconciler import StateReconciler, ReconcilerConfig
from monitoring.alerts import send_alert

# Initialize reconciler
config = ReconcilerConfig(
    interval_seconds=300,
    warning_threshold_lamports=5000000,
    critical_threshold_lamports=50000000,
)

reconciler = StateReconciler(
    rpc_client=connection,
    wallet_pubkey=wallet.pubkey(),
    portfolio_state=portfolio,
    config=config,
    dry_run=False,
)

# Check and reconcile
adjustment = await reconciler.check_and_reconcile()

if adjustment:
    level = reconciler.get_alert_level(adjustment)
    message = compose_balance_discrepancy_alert(
        delta_lamports=adjustment.delta_lamports,
        onchain_balance=adjustment.onchain_balance_lamports,
        local_balance=adjustment.local_balance_lamports_before,
        reason=adjustment.reason,
        adjusted=adjustment.adjusted,
    )
    await send_alert(message, level=level)
```

## Background Worker

```python
from monitoring.state_reconciler_worker import run_reconciler

# Run reconciler as background task
await run_reconciler(
    rpc_client=connection,
    wallet_pubkey=wallet.pubkey(),
    portfolio_state=portfolio,
    config=config,
    dry_run=False,
)
```

## Hard Rules

| Rule | Enforcement |
|------|-------------|
| Live mode only | Reconciler only initialized in live mode |
| Non-blocking | Async sleep-based loop, no blocking calls |
| Dry-run support | `--dry-run` prevents adjustment application |
| Explicit records | All changes go through `BalanceAdjustment` |
| Alert thresholds | Alerts only when delta > threshold |
| No stdout writes | Logs to stderr, no summary interference |

## Alert Levels

| Delta Range | Level | Action |
|-------------|-------|--------|
| < 5M lamports (0.005 SOL) | None | No alert |
| 5M - 50M lamports | WARNING | Send alert |
| >= 50M lamports | CRITICAL | Send alert + possible action |

## Testing

### Smoke Test

```bash
bash scripts/state_reconciler_smoke.sh
```

**Expected Output:**
```
[state_reconciler_smoke] Starting PR-X.1 smoke tests (mock mode)...
[state_reconciler_smoke] Testing BalanceAdjustment dataclass...
[state_reconciler_smoke] Test 1 PASSED: BalanceAdjustment works
[state_reconciler_smoke] Testing ReconcilerConfig...
[state_reconciler_smoke] Test 2 PASSED: ReconcilerConfig works
[state_reconciler_smoke] Testing StateReconciler...
[state_reconciler_smoke] Adjustment created: delta=50000000
[state_reconciler_smoke] Test 3 PASSED: StateReconciler works
[state_reconciler_smoke] Testing threshold behavior...
[state_reconciler_smoke] Test 4 PASSED: Threshold behavior works
[state_reconciler_smoke] Testing alert level determination...
[state_reconciler_smoke] Test 5 PASSED: Alert levels work
[state_reconciler_smoke] Testing adjustment export...
[state_reconciler_smoke] Test 6 PASSED: Export functionality works
[state_reconciler_smoke] Results: 6 passed, 0 failed
[state_reconciler_smoke] OK
```

## Integration Points

### With PortfolioState

```python
class PortfolioState:
    def apply_adjustment(self, adjustment: BalanceAdjustment) -> None:
        """Apply a balance adjustment to local state."""
        self.bankroll_lamports = adjustment.onchain_balance_lamports
```

### With Telegram Alerts

```python
from monitoring.alerts import (
    ALERT_BALANCE_DISCREPANCY,
    compose_balance_discrepancy_alert,
)

await send_alert(
    level="WARNING",
    type=ALERT_BALANCE_DISCREPANCY,
    message=compose_balance_discrepancy_alert(...),
)
```

## Reject Reasons

All balance discrepancy reasons are available:

```python
from integration.reject_reasons import (
    BALANCE_DISCREPANCY_DETECTED,
    assert_reason_known,
)

assert_reason_known(BALANCE_DISCREPANCY_DETECTED)
```

## Future Enhancements

1. **Automatic transaction matching** - Link missed tx signatures
2. **Historical trend analysis** - Detect gradual drift
3. **Multi-wallet support** - Reconcile all tracked wallets
4. **Adjustment rollback** - Ability to undo incorrect adjustments
5. **Prometheus metrics** - Export reconciliation stats
