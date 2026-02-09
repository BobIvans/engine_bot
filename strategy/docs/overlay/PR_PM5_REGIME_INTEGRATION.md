# PR-PM.5: Risk Regime Integration into Signal Pipeline

> **Status:** Implemented  
> **Owner:** Strategy Team  
> **Version:** 1.0

## Overview

This PR integrates the Polymarket `risk_regime` scalar [-1.0..+1.0] into the +EV signal pipeline as a multiplicative corrector. The integration allows the strategy to adjust edge calculations based on overall market sentiment derived from Polymarket prediction markets.

## Formula

### Edge Correction Formula

```
edge_final = edge_raw * (1 + alpha * risk_regime)
```

Where:
- `edge_raw`: Raw edge before regime adjustment (from EV calculation)
- `risk_regime`: Market regime from Polymarket [-1.0, +1.0]
  - `+1.0`: Strongly bullish market conditions
  - `0.0`: Neutral market conditions
  - `-1.0`: Strongly bearish market conditions
- `alpha`: Configurable weight parameter (default: 0.20, range: [0.0, 0.5])
- `edge_final`: Edge after regime adjustment

### Example Calculations

| edge_raw | risk_regime | alpha | edge_final | Interpretation |
|----------|-------------|-------|------------|----------------|
| 0.06 | +0.75 | 0.20 | 0.069 | Bullish regime amplifies edge by 15% |
| 0.04 | +0.75 | 0.20 | 0.046 | Bullish regime amplifies edge by 15% |
| 0.05 | 0.00 | 0.20 | 0.050 | Neutral regime, no adjustment |
| 0.10 | -1.00 | 0.20 | 0.080 | Bearish regime reduces edge by 20% |

## Parameter Configuration

### YAML Configuration

```yaml
# strategy/config/params_base.yaml

regime:
  alpha: 0.20  # Range: [0.0, 0.5]
```

### Default Bounds

| Parameter | Min | Max | Default | Description |
|-----------|-----|-----|---------|-------------|
| `alpha` | 0.0 | 0.5 | 0.20 | Regime adjustment weight |
| `risk_regime` | -1.0 | +1.0 | 0.0 | Market regime from Polymarket |

## Signal Schema Extension

All signals now include the following fields:

```json
{
  "risk_regime": {
    "type": "number",
    "minimum": -1.0,
    "maximum": 1.0,
    "description": "Risk regime from Polymarket [-1.0, +1.0]"
  },
  "edge_raw": {
    "type": "number",
    "description": "Raw edge before regime adjustment"
  },
  "edge_final": {
    "type": "number",
    "description": "Edge after regime adjustment"
  },
  "regime_alpha": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 0.5,
    "description": "Configurable weight for regime adjustment"
  }
}
```

## Missing Regime Handling

### Behavior When `regime_timeline.parquet` is Missing or Empty

1. **File not found**: `risk_regime` defaults to `0.0` (neutral)
2. **Empty file**: `risk_regime` defaults to `0.0` (neutral)
3. **No records matching timestamp**: `risk_regime` defaults to `0.0` (neutral)

When `risk_regime = 0.0`:
- `edge_final = edge_raw * (1 + alpha * 0.0) = edge_raw`
- No correction is applied

## CLI Flag: `--skip-regime-adjustment`

### Purpose

Fully disables regime adjustment for testing or fallback scenarios.

### Behavior

When `--skip-regime-adjustment` is set:
- `edge_final = edge_raw` (no correction applied)
- `risk_regime = 0.0` (fields still populated but no effect)
- `regime_alpha` remains in config but is not used

### Example Usage

```bash
# Run pipeline without regime adjustment
python3 -m integration.paper_pipeline \
  --input trades.jsonl \
  --skip-regime-adjustment

# Run pipeline with regime adjustment
python3 -m integration.paper_pipeline \
  --input trades.jsonl \
  --regime-input regime_timeline.parquet
```

## Integration Points

### Modified Files

| File | Changes |
|------|---------|
| `strategy/logic.py` | Added `adjust_edge_for_regime()` pure function; updated `decide_on_wallet_buy()` |
| `integration/decision_stage.py` | Added regime loading from parquet; integrated with decision logic |
| `strategy/config/params_base.yaml` | Added `regime.alpha` parameter |
| `integration/schemas/signal_schema.json` | Added `risk_regime`, `edge_raw`, `edge_final`, `regime_alpha` fields |

### New Files

| File | Purpose |
|------|---------|
| `integration/fixtures/sentiment/regime_timeline_sample.parquet` | Test fixture for smoke tests |
| `scripts/regime_integration_smoke.sh` | Smoke test for regime integration |
| `strategy/docs/overlay/PR_PM5_REGIME_INTEGRATION.md` | This documentation |

## Backward Compatibility

- **Flag `--skip-regime-adjustment`**: Fully disables correction, sets `risk_regime = 0.0`
- **Schema compliance**: All 4 new fields are mandatory in output signals (even when skipped)
- **Existing signals**: Continue to work with default `risk_regime = 0.0`

## Testing

### Smoke Test

```bash
bash scripts/regime_integration_smoke.sh
```

### Expected Output

```
[regime_integration_smoke] Testing adjust_edge_for_regime() pure function...
  OK: adjust_edge_for_regime(0.06, 0.75, 0.20) = 0.069
  OK: adjust_edge_for_regime(0.04, 0.75, 0.20) = 0.046
  OK: adjust_edge_for_regime(0.03, 0.75, 0.20) = 0.035
[regime_integration_smoke] PASS: adjust_edge_for_regime() pure function
[regime_integration_smoke] OK
```

### Validation

```bash
# Verify formula with alpha=0.20, risk_regime=0.75
python3 -c "
from strategy.logic import adjust_edge_for_regime
result = adjust_edge_for_regime(0.06, 0.75, 0.20)
assert abs(result - 0.069) < 0.001, f'Expected 0.069, got {result}'
print('Formula validation passed!')
"
```

## GREP Points

```bash
# Find adjust_edge_for_regime function
grep -n "adjust_edge_for_regime" strategy/logic.py

# Find edge_final usage
grep -n "edge_final" strategy/logic.py

# Find risk_regime in schema
grep -n "risk_regime" strategy/schemas/signal_schema.json

# Find regime_alpha in config
grep -n "regime_alpha" strategy/config/params_base.yaml

# Find PR-PM.5 documentation
grep -n "PR-PM.5" strategy/docs/overlay/PR_PM5_REGIME_INTEGRATION.md

# Find smoke test marker
grep -n "\[regime_integration_smoke\] OK" scripts/regime_integration_smoke.sh

# Find CLI flag
grep -n "--skip-regime-adjustment" integration/paper_pipeline.py
```

## Known Limitations

1. **Negative edge_final**: When `risk_regime = -1.0` and `alpha > 0`, `edge_final` may become negative. This is intentional—the +EV gate will automatically reject such signals.

2. **External risk_regime**: When an external `risk_regime` is provided (non-zero), it takes precedence over the computed regime from PolymarketSnapshot.

3. **Parquet format**: The regime timeline must be in Parquet format with columns: `ts`, `risk_regime`, `bullish_markets`, `bearish_markets`, `confidence`, `source_snapshot_id`.

## Related Documentation

- [Strategy Manifest](../docs/strategy_manifest.md)
- [Decision Logic](../strategy/logic.py)
- [Decision Stage](../integration/decision_stage.py)
