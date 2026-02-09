# PR-E.6 Execution Quality Monitor

**Status:** Implemented  
**Owner:** @ivansbobrovs  
**Created:** 2024-01-15

## Overview

Execution Quality Monitor tracks key execution metrics to detect degradation in fill quality, slippage, and latency. It compares paper (simulated) vs live execution to surface issues before they impact PnL.

## Key Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `fill_rate` | filled_signals / total_signals | Drop >10% vs paper |
| `avg_realized_slippage_bps` | Mean realized slippage in bps | >100 bps |
| `latency_p90_ms` | 90th percentile latency | +100ms vs paper |
| `partial_fill_ratio` | partial_fills / total_fills | >20% |

## Usage

```python
from monitoring.execution_quality_monitor import ExecutionQualityMonitor

# Initialize with alert thresholds
monitor = ExecutionQualityMonitor(slippage_threshold_bps=100.0)

# Add fills from different sources
monitor.add_fills("paper", paper_fills_list)
monitor.add_fills("live", live_fills_list)

# Get metrics for a source
metrics = monitor.get_metrics("paper")
print(f"Fill rate: {metrics.fill_rate:.2%}")
print(f"Avg slippage: {metrics.avg_realized_slippage_bps:.1f} bps")

# Compare paper vs live
comparison = monitor.compare_paper_live()
print(f"Slippage delta: {comparison.delta_avg_slippage_bps:.1f} bps")

# Generate full report with alerts
report = monitor.generate_report()
print(f"Alerts: {report['alerts']}")
```

## FillRecord Schema

```python
@dataclass
class FillRecord:
    signal_id: str           # Unique signal identifier
    side: str               # BUY | SELL
    estimated_price: float  # Expected fill price
    realized_price: float   # Actual fill price
    realized_slippage_bps: float  # Slippage in basis points
    latency_ms: int         # Fill latency in milliseconds
    fill_status: str       # filled | partial | none
    size_initial: float    # Original order size
    size_remaining: float   # Remaining size (partial fills)
    timestamp: str         # ISO 8601 timestamp
    token_mint: str        # Token address
    wallet: str            # Wallet address
```

## Integration Points

### Integration with sim_fill.py

The `FillResult` from [`execution/sim_fill.py`](execution/sim_fill.py) should include `realized_slippage_bps` for monitoring:

```python
from execution.sim_fill import simulate_fill
from monitoring.execution_quality_monitor import ExecutionQualityMonitor

result = simulate_fill(
    side="BUY",
    mid_price=1.0,
    size_usd=100.0,
    snapshot=snapshot,
    execution_cfg=config,
    mode_ttl_sec=120,
    seed=42,
)

fill_record = FillRecord(
    signal_id=signal_id,
    side=side,
    estimated_price=estimated_price,
    realized_price=result.fill_price,
    realized_slippage_bps=result.slippage_bps,
    latency_ms=result.latency_ms,
    fill_status=result.status,
    size_initial=size_usd,
    size_remaining=0.0,
    timestamp=datetime.utcnow().isoformat(),
)

monitor.add_fill_record("live", fill_record)
```

### Integration with live_executor.py

For live execution, capture fills in real-time:

```python
from monitoring.execution_quality_monitor import ExecutionQualityMonitor

monitor = ExecutionQualityMonitor()

# After each live fill
async def on_fill_complete(fill: LiveFill):
    record = FillRecord(
        signal_id=fill.signal_id,
        side=fill.side,
        estimated_price=fill.estimated_price,
        realized_price=fill.realized_price,
        realized_slippage_bps=calc_slippage_bps(fill),
        latency_ms=fill.latency_ms,
        fill_status="filled",
        size_initial=fill.size,
        size_remaining=0.0,
        timestamp=fill.timestamp.isoformat(),
    )
    monitor.add_fill_record("live", record)

# Periodic health check
def health_check():
    report = monitor.generate_report()
    if any(a["level"] == "WARNING" for a in report["alerts"]):
        send_alert(report["alerts"])
```

## Smoke Test

```bash
./scripts/execution_quality_smoke.sh
```

Expected output:
```
[execution_quality_smoke] Running Execution Quality Monitor smoke test...
[execution_quality_smoke] Test 1: FillRecord creation...
[execution_quality_smoke] Test 1 passed: FillRecord works
...
[execution_quality_smoke] All tests passed successfully! ✅
[execution_quality_smoke] OK ✅
```

## GREP Points

```bash
grep -n "PR-E.6" strategy/docs/overlay/PR-E.6.md           # Line 1
grep -n "ExecutionQualityMonitor" monitoring/execution_quality_monitor.py  # Multiple matches
grep -n "realized_slippage_bps" execution/sim_fill.py       # Line 30 (FillResult.slippage_bps)
```

## Related Files

| File | Purpose |
|------|---------|
| [`monitoring/execution_quality_monitor.py`](monitoring/execution_quality_monitor.py) | Main monitoring module |
| [`execution/sim_fill.py`](execution/sim_fill.py) | Fill simulation with slippage |
| [`execution/latency_model.py`](execution/latency_model.py) | Latency distribution model |
| [`integration/fixtures/execution_quality/paper_fills_sample.jsonl`](integration/fixtures/execution_quality/paper_fills_sample.jsonl) | Paper fill fixtures |
| [`integration/fixtures/execution_quality/live_fills_sample.jsonl`](integration/fixtures/execution_quality/live_fills_sample.jsonl) | Live fill fixtures |
| [`scripts/execution_quality_smoke.sh`](scripts/execution_quality_smoke.sh) | Smoke test |

## Hard Rules

1. **Lightweight**: No main loop impact; passive monitoring
2. **Dual mode**: Works in both paper and live pipelines
3. **Alert levels**: WARNING for degradations, ERROR for critical issues
4. **Deterministic**: Fully testable offline with fixtures
5. **No network calls**: All processing is local
