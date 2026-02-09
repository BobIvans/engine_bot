# PR-ML.5 — Calibration Loader Integration

**Status:** `IN PROGRESS`  
**Created:** 2026-02-09  
**Owner:** ML Subsystem  

## Overview

This PR implements calibration loader integration for transforming raw model predictions (`p_model_raw`) into calibrated probabilities (`p_model_calibrated`). Proper calibration ensures that predicted scores match empirical success rates.

## Motivation

Raw model outputs often suffer from:
- **Overconfidence**: Predicted probabilities are systematically higher than actual win rates
- **Miscalibration**: A `p_model=0.70` might win only 55% of the time

Calibration fixes this by:
- Mapping raw scores to empirically accurate probabilities
- Improving EV calculations
- Better risk management

## Calibration Methods

### Platt Scaling

```
p_calibrated = 1 / (1 + exp(a × p_raw + b))
```

Where `a < 0` corrects overconfident predictions.

**Example:**
- `p_raw=0.60` → `p_cal≈0.52`
- `p_raw=0.80` → `p_cal≈0.68`

### Isotonic Regression

Piecewise-linear monotonic function through control points:

```json
{
  "x": [0.0, 0.3, 0.5, 0.7, 1.0],
  "y": [0.0, 0.25, 0.45, 0.62, 0.85]
}
```

**Example:**
- `p_raw=0.40` → `p_cal≈0.35`
- `p_raw=0.90` → `p_cal≈0.78`

## Configuration

In `strategy/config/params_base.yaml`:

```yaml
model:
  calibration:
    enabled: true
    model_version: "v1_20250201"  # or null to disable
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `p_model_raw` | float | Raw model prediction [0.0, 1.0] |
| `p_model_calibrated` | float | Calibrated probability [0.0, 1.0] |
| `calibration_version` | string | Version of calibration used |

## Implementation

### Calibration Loader

```python
from integration.models.calibration_loader import CalibrationLoader

loader = CalibrationLoader(
    model_version="v1_20250201",
    allow_calibration=True
)

p_calibrated = loader.apply(p_raw=0.60)  # Returns ~0.52
```

### Integration in Feature Builder

```python
# Global cached loader
_CALIBRATION_LOADER: Optional[CalibrationLoader] = None

def build_features(...) -> FeatureVector:
    # Calculate raw prediction
    features.p_model_raw = model.predict(features)
    
    # Apply calibration
    if _CALIBRATION_LOADER:
        features.p_model_calibrated = _CALIBRATION_LOADER.apply(features.p_model_raw)
    else:
        features.p_model_calibrated = features.p_model_raw
    
    return features
```

### Integration in Decision Logic

```python
def decide_on_wallet_buy(...):
    # Use CALIBRATED score in EV formula
    edge_raw = (
        features.p_model_calibrated * config.mu_win +
        (1.0 - features.p_model_calibrated) * config.mu_loss -
        config.cost_fixed
    )
    # ... rest of logic
```

## Quality Metrics

| Metric | Good | Excellent |
|--------|------|-----------|
| Brier Score | < 0.025 | < 0.015 |
| ECE | < 0.03 | < 0.02 |

### Brier Score

```
BS = (1/N) × Σ(p_calibrated - outcome)²
```

Lower is better. Range: [0, 1]

### Expected Calibration Error (ECE)

```
ECE = Σ(|calibrated_bin_avg - bin_avg|) / N
```

Measures average calibration gap across confidence bins.

## Fixtures

### Platt Calibration

```json
{
  "model_version": "v1_20250201",
  "calibration_type": "platt",
  "params": {"a": -1.85, "b": 0.32},
  "trained_on": "2025-02-01",
  "metrics": {"brier_score": 0.018, "ece": 0.022, "samples": 12500}
}
```

### Isotonic Calibration

```json
{
  "model_version": "v2_20250205",
  "calibration_type": "isotonic",
  "params": {
    "x": [0.0, 0.3, 0.5, 0.7, 1.0],
    "y": [0.0, 0.25, 0.45, 0.62, 0.85]
  },
  "trained_on": "2025-02-05",
  "metrics": {"brier_score": 0.015, "ece": 0.018, "samples": 15200}
}
```

## Safety Features

1. **Monotonicity Validation**: Isotonic curves must be monotonically increasing
2. **Range Capping**: Output always clamped to [0.0, 1.0]
3. **Fallback**: On any error, falls back to identity (`p_cal = p_raw`)
4. **Schema Validation**: All calibration files validated on load

## Update Strategy

- **Weekly Retraining**: Calibrate on last 7 days of data
- **Rollback Trigger**: If Brier score degrades by 20%, auto-rollback
- **Versioning**: Each calibration has unique version identifier

## Smoke Test

```bash
bash scripts/calibration_smoke.sh
```

Expected output:
```
[calibration] loaded platt calibrator v=v1_20250201 (Brier=0.018, ECE=0.022)
[calibration_smoke] calibrated 3 scores: [0.40→0.38, 0.60→0.52, 0.80→0.68]
[calibration_smoke] OK
```

## GREP Points

```bash
grep -n "CalibrationLoader" integration/models/calibration_loader.py
grep -n "p_model_calibrated" strategy/schemas/feature_vector_schema.json
grep -n "apply_calibration" strategy/feature_builder.py
grep -n "platt" strategy/schemas/calibration_schema.json
grep -n "isotonic" strategy/schemas/calibration_schema.json
grep -n "PR-ML.5" strategy/docs/overlay/PR_ML5_CALIBRATION_LOADER.md
grep -n "\[calibration_smoke\]" scripts/calibration_smoke.sh
```

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `integration/models/calibration_loader.py` | Created | Calibration loader with Platt/Isotonic support |
| `strategy/schemas/calibration_schema.json` | Created | Schema for calibration files |
| `integration/fixtures/ml/calibration_platt_sample.json` | Created | Platt calibration fixture |
| `integration/fixtures/ml/calibration_isotonic_sample.json` | Created | Isotonic calibration fixture |
| `scripts/calibration_smoke.sh` | Created | Smoke test |
| `strategy/feature_builder.py` | Modified | Integration of calibration |
| `strategy/schemas/feature_vector_schema.json` | Modified | Added p_model_calibrated |
| `strategy/logic.py` | Modified | Use calibrated score in EV |
| `strategy/config/params_base.yaml` | Modified | Added calibration config |
| `strategy/docs/overlay/PR_ML5_CALIBRATION_LOADER.md` | Created | This documentation |
| `scripts/overlay_lint.sh` | Modified | Added smoke test to pipeline |

## Backward Compatibility

- Flag `--allow-calibration` defaults to `True`
- When disabled, `p_model_calibrated = p_model_raw`
- All new fields have default values
