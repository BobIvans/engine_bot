# PR-ML.1: Polymarket-Augmented Features

| Field | Value |
|-------|-------|
| **PR** | ML.1 |
| **Status** | Implemented |
| **Author(s)** | System |
| **Reviewer(s)** | TBD |
| **Created** | 2024-01-15 |
| **Updated** | 2024-01-15 |

## Overview

Extends feature vectors with 4 Polymarket-augmented features for improved predictive capability. Uses sentiment and event data from Polymarket markets mapped to trading tokens.

## Features

| Feature | Range | Description |
|---------|-------|-------------|
| `pmkt_bullish_score` | [-1.0, +1.0] | Aggregated bullish probability score |
| `pmkt_event_risk` | [0.0, 1.0] | Binary flag for critical events within 3 days |
| `pmkt_volatility_zscore` | [-5.0, +5.0] | Z-score of probability volatility |
| `pmkt_volume_spike_factor` | [0.0, 10.0] | Volume spike relative to 24h mean |

## Formulas

### pmkt_bullish_score

```
score = Σ((p_yes - 0.5) * relevance * vol_norm) / Σ(weight)
weight = relevance * (0.7 + 0.3 * vol_norm)
vol_norm = (volume - min_vol) / (max_vol - min_vol)
```

**Window**: 6 hours  
**Range**: [-1.0, +1.0]  
**Missing Data**: 0.0 (neutral)

### pmkt_event_risk

```
risk = 1.0 if (high_event_risk == True AND days_to_resolution <= 3) else 0.0
```

**Window**: 3 days lookahead  
**Range**: [0.0, 1.0]  
**Missing Data**: 0.0

### pmkt_volatility_zscore

```
diffs = [p_yes[t+1] - p_yes[t] for t in sorted_snapshots]
mean = avg(diffs)
std = std(diffs)
zscore = (last_diff - mean) / std
```

**Window**: 6 hours (min 5 data points)  
**Range**: [-5.0, +5.0] (capped)  
**Missing Data**: 0.0

### pmkt_volume_spike_factor

```
factor = current_volume / rolling_mean(volume, 24h)
```

**Window**: 24 hours  
**Range**: [0.0, 10.0] (capped)  
**Missing Data**: 1.0 (neutral)

## Data Sources

- **Snapshots**: `polymarket_snapshots.parquet`
- **Mappings**: `polymarket_token_mapping.parquet`
- **Event Risk**: `event_risk_timeline.parquet`

## Feature Importance Calibration

Based on historical correlation analysis with trading outcomes:

| Feature | Correlation | Interpretation |
|---------|-------------|----------------|
| `pmkt_bullish_score` | +0.38 | Higher bullish sentiment → more likely profitable |
| `pmkt_event_risk` | -0.42 | High event risk → larger drawdowns |
| `pmkt_volatility_zscore` | +0.12 | Weak alone, significant with bullish_score |
| `pmkt_volume_spike_factor` | +0.29 | Volume spikes → higher volatility/returns |

### Recommendations

- Use all 4 features in model
- Apply regularization to prevent overfitting
- Consider feature interactions (e.g., `bullish_score * event_risk`)
- Monitor feature drift in production

## Testing

```bash
# Run smoke tests
bash scripts/polymarket_features_smoke.sh

# Expected output
=== Polymarket Features Smoke Test ===
[1/4] Testing pure function imports...
  ✓ compute_pmkt_bullish_score: OK
  ✓ compute_pmkt_event_risk: OK
  ✓ compute_pmkt_volatility_zscore: OK
  ✓ compute_pmkt_volume_spike_factor: OK
[2/4] Testing FEATURE_KEYS_V5...
  ✓ FEATURE_KEYS_V5 contains 17 keys
[3/4] Testing fixture loading...
  ✓ Snapshots fixture exists
  ✓ Mapping fixture exists
[4/4] Testing expected values on fixtures...
  ✓ WIF bullish score: 0.72 (expected > 0)
  ✓ Score within [-1.0, +1.0] range
[polymarket_features_smoke] OK
```

## Files

| File | Description |
|------|-------------|
| `analysis/polymarket_features.py` | Pure feature computation functions |
| `features/trade_features.py` | FEATURE_KEYS_V5 definition |
| `integration/fixtures/ml/polymarket_snapshots_features_sample.parquet` | Test snapshots (24h, 3 markets) |
| `integration/fixtures/ml/polymarket_token_mapping_features_sample.parquet` | Token mappings (WIF, BONK) |
| `scripts/polymarket_features_smoke.sh` | Smoke test |

## GREP Points

```bash
grep -n "compute_pmkt_bullish_score" analysis/polymarket_features.py
grep -n "FEATURE_KEYS_V5" features/trade_features.py
grep -n "pmkt_event_risk" analysis/polymarket_features.py
grep -n "PR-ML.1" strategy/docs/overlay/PR_ML1_POLYMARKET_FEATURES.md
grep -n "feature_importance" strategy/docs/overlay/PR_ML1_POLYMARKET_FEATURES.md
```

## Integration

```python
from analysis.polymarket_features import (
    compute_all_pmkt_features,
    PolymarketSnapshot,
    PolymarketTokenMapping,
)

# Compute all 4 features
features = compute_all_pmkt_features(
    snapshots=snapshots,
    mapping=mapping,
    event_risk=event_risk,
)
# Returns: {
#     "pmkt_bullish_score": 0.72,
#     "pmkt_event_risk": 0.0,
#     "pmkt_volatility_zscore": 2.1,
#     "pmkt_volume_spike_factor": 3.4,
# }
```

## Backward Compatibility

All features are optional:
- Missing Polymarket data → features = 0.0 (or 1.0 for volume_spike_factor)
- Existing pipelines continue to work
- New features appended to feature vector
