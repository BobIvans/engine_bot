# PR-RM.1 — Polymarket-Aware Position Sizing

**Status:** `IN PROGRESS`  
**Created:** 2026-02-09  
**Owner:** Risk Management Subsystem  

## Overview

This PR implements adaptive position sizing based on Polymarket risk regime signals. When the market is in a risk-on regime (`risk_regime > 0`), the strategy increases position sizes up to 5% of capital. In risk-off regime (`risk_regime < 0`), positions are reduced to 1-2% of capital.

## Motivation

Position sizing is a critical risk management lever. By dynamically adjusting position sizes based on market regime, we can:

- **Increase exposure** during favorable (risk-on) conditions to capture more alpha
- **Decrease exposure** during unfavorable (risk-off) conditions to preserve capital
- **Maintain discipline** through systematic, regime-aware position management

## Formula

### Base Formula

```
position_pct_adjusted = base_position_pct × (1 + β × risk_regime)
```

Where:
- `base_position_pct`: Default position size (2% of capital)
- `β` (risk_beta): Sensitivity coefficient (0.5 = ±25% adjustment at ±1.0 regime)
- `risk_regime`: Polymarket regime scalar (-1.0 to +1.0)

### Constraints

```
min_position_pct_risk_off ≤ position_pct_adjusted ≤ max_position_pct_risk_on
```

### Absolute Safety Caps

```
0.01 ≤ position_pct_adjusted ≤ 0.05  # 1% to 5% of capital
```

## Examples

| risk_regime | base_pct | β | Raw Calculation | Adjusted | Notes |
|-------------|----------|---|----------------|----------|-------|
| +0.85 | 0.02 | 0.5 | 2% × (1 + 0.5×0.85) = 2.85% | 2.85% | Risk-on |
| +1.00 | 0.02 | 0.5 | 2% × (1 + 0.5×1.0) = 3.0% | 3.0% | Max regime |
| 0.00 | 0.02 | 0.5 | 2% × (1 + 0.5×0) = 2.0% | 2.0% | Neutral |
| -0.92 | 0.02 | 0.5 | 2% × (1 - 0.5×0.92) = 1.08% | 1.0% | Min capped |
| -1.00 | 0.02 | 0.5 | 2% × (1 - 0.5×1.0) = 1.0% | 1.0% | Min regime |

## Safety Gates

1. **Minimum Position**: Never trade below 1% of capital
2. **Maximum Position**: Never trade above 5% of capital
3. **Minimum Trade Size**: If adjusted position < $500, skip the trade
4. **Maximum Trade Size**: If adjusted position > $5000, cap at $5000

## Configuration

In `strategy/config/params_base.yaml`:

```yaml
# Position sizing parameters
base_position_pct: 0.02              # 2% base position size
risk_beta: 0.5                        # Regime sensitivity
max_position_pct_risk_on: 0.05        # Max 5% in risk-on
min_position_pct_risk_off: 0.01       # Min 1% in risk-off
max_trade_size_usd: 5000.0           # Absolute max trade size
min_trade_size_usd: 500.0            # Min trade to execute
max_kelly_fraction: 0.25              # Kelly cap

# Feature flags
allow_risk_aware_sizing: true        # Enable adaptive sizing
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `position_pct_raw` | float | Base position percentage before regime adjustment |
| `position_pct_adjusted` | float | Final position percentage after regime adjustment |
| `risk_regime_used` | float | Risk regime value used for adjustment |
| `position_sizing_method` | string | `"fixed"`, `"risk_aware"`, or `"fallback"` |
| `position_usd` | float | Dollar amount of the position |

## Implementation

### Core Function

```python
def compute_risk_aware_position_pct(
    base_pct: float,
    risk_regime: float,
    risk_beta: float,
    min_pct: float,
    max_pct: float,
    allow_risk_aware: bool = True
) -> Tuple[float, str]:
    """
    Calculate adaptive position size based on risk regime.
    
    Returns:
        Tuple of (adjusted_percentage, sizing_method)
    """
    if not allow_risk_aware or risk_regime is None:
        return base_pct, "fixed"
    
    # Apply adaptive formula
    adjusted = base_pct * (1.0 + risk_beta * risk_regime)
    
    # Apply regime constraints
    adjusted = max(min_pct, min(max_pct, adjusted))
    
    # Apply absolute safety caps
    adjusted = max(0.01, min(0.05, adjusted))
    
    return adjusted, "risk_aware"
```

### Integration in decide_on_wallet_buy()

```python
# === Risk-Aware Position Sizing ===
position_pct_raw = config.base_position_pct
position_pct_adjusted, sizing_method = compute_risk_aware_position_pct(
    base_pct=config.base_position_pct,
    risk_regime=risk_regime,
    risk_beta=config.risk_beta,
    min_pct=config.min_position_pct_risk_off,
    max_pct=config.max_position_pct_risk_on,
    allow_risk_aware=config.allow_risk_aware_sizing
)

# Calculate USD amounts
position_usd = available_capital_usd * position_pct_adjusted
position_usd = min(position_usd, config.max_trade_size_usd)

# Decision logic
decision = "buy" if (
    edge_final > config.edge_threshold and 
    position_usd >= config.min_trade_size_usd
) else "hold"
```

## CLI Integration

```bash
# Enable adaptive sizing (default: True)
python3 -m integration.paper_pipeline --input trades.jsonl --allow-risk-aware-sizing

# Disable adaptive sizing (use base position only)
python3 -m integration.paper_pipeline --input trades.jsonl --no-allow-risk-aware-sizing
```

## Smoke Test

```bash
bash scripts/position_sizing_smoke.sh
```

Expected output:
```
[position_sizing_smoke] Starting position sizing smoke test...
[position_sizing_smoke] Test 1: Importing logic.py... OK
[position_sizing_smoke] Test 2: Validating fixture... OK
[position_sizing_smoke] risk_regime=+0.85 → position 2.85% ($285) of $10k capital (risk-on)
[position_sizing_smoke] risk_regime=0.00 → position 2.0% ($200) of $10k capital (neutral)
[position_sizing_smoke] risk_regime=-0.92 → position 1.0% ($100) of $10k capital (risk-off, min threshold)
[position_sizing_smoke] validated adaptive sizing across 3 risk regimes
[position_sizing_smoke] OK
```

## Expected Metrics

```json
{
  "signals_processed": 3,
  "avg_position_pct": 0.0257,
  "risk_regime_distribution": {
    "risk_on": 1,
    "neutral": 1,
    "risk_off": 1
  }
}
```

## Fixtures

Test data in `integration/fixtures/risk/position_sizing_sample.json`:

| risk_regime | edge_final | expected_position_pct |
|-------------|------------|---------------------|
| +0.85 | 0.07 | 0.047 (capped by max) |
| 0.00 | 0.05 | 0.020 (base) |
| -0.92 | 0.04 | 0.010 (min capped) |

## GREP Points

```bash
grep -n "compute_risk_aware_position_pct" strategy/logic.py
grep -n "position_pct_adjusted" strategy/schemas/signal_schema.json
grep -n "risk_beta" strategy/config/params_base.yaml
grep -n "PR-RM.1" strategy/docs/overlay/PR_RM1_POSITION_SIZING.md
grep -n "\[position_sizing_smoke\]" scripts/position_sizing_smoke.sh
grep -n "--allow-risk-aware-sizing" integration/paper_pipeline.py
```

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `strategy/logic.py` | Modified | Added `compute_risk_aware_position_pct()` and integration |
| `strategy/config/params_base.yaml` | Modified | Added position sizing parameters |
| `strategy/schemas/signal_schema.json` | Modified | Added position sizing fields |
| `scripts/position_sizing_smoke.sh` | Created | Smoke test script |
| `integration/fixtures/risk/position_sizing_sample.json` | Created | Test fixtures |
| `strategy/docs/overlay/PR_RM1_POSITION_SIZING.md` | Created | This documentation |
| `scripts/overlay_lint.sh` | Modified | Added smoke test to pipeline |

## Backward Compatibility

- Flag `--allow-risk-aware-sizing` defaults to `True`
- When disabled, all positions use `base_position_pct`
- All new fields have default values in existing code paths

## Future Enhancements

1. **Volatility-adjusted sizing**: Scale positions inversely with realized volatility
2. **Drawdown-based reduction**: Reduce positions after consecutive losses
3. **Correlation-aware sizing**: Reduce correlated positions across assets
4. **Machine learning**: Learn optimal regime-beta relationship from backtests
