# PR-ML.4 — Survival Analysis Model (Hazard Scoring)

**Status:** `IN PROGRESS`  
**Created:** 2026-02-09  
**Owner:** ML Subsystem  

## Overview

This PR implements a survival analysis model for predicting token crash probability based on real-time on-chain and market indicators. The model produces a **hazard score** in `[0.0, 1.0]` that feeds into the emergency exit trigger and position sizing logic.

## Motivation

Tokens can "rug" or crash due to various on-chain signals. This model quantifies crash probability using:
- Liquidity behavior (rapid drops indicate panic selling)
- Top holder behavior (selling = signal)
- Contract features (mint authority = risk)
- Smart money cluster behavior
- Market event risk

## Formula

### Raw Hazard Score

```
hazard_raw = σ(
    w_liq * liquidity_drop_10s +
    w_top * top_holder_sell_ratio +
    w_mint * mint_auth_exists +
    w_cluster * cluster_sell_pressure +
    w_pmkt * pmkt_event_risk
)
```

Where:
- `σ(x) = 1 / (1 + exp(-k * (x - x0)))` is a sigmoid with `k=10`, `x0=0.5`
- Weights:
  - `liquidity_drop_10s`: `3.2`
  - `top_holder_sell_ratio`: `2.8`
  - `mint_auth_exists`: `1.5`
  - `cluster_sell_pressure`: `2.1`
  - `pmkt_event_risk`: `1.0`

### Calibrated Hazard Score

```
hazard_calibrated = interpolate(hazard_raw, calibration_curve)
```

Default calibration curve:
| Raw | Calibrated |
|-----|------------|
| 0.0 | 0.0        |
| 0.2 | 0.15       |
| 0.4 | 0.35       |
| 0.6 | 0.65       |
| 0.8 | 0.85       |
| 1.0 | 1.0        |

### Emergency Exit Trigger

```
if hazard_calibrated >= hazard_threshold:
    trigger_emergency_exit()
```

Default `hazard_threshold = 0.65`.

## Features

### Input Features

| Feature | Type | Range | Description |
|---------|------|-------|-------------|
| `liquidity_drop_10s` | float | [0.0, 1.0] | % of liquidity lost in first 10s of trade |
| `top_holder_sell_ratio` | float | [0.0, 1.0] | % of top 10 holders selling |
| `mint_auth_exists` | float | {0.0, 1.0} | Whether mint authority exists |
| `cluster_sell_pressure` | float | [0.0, 1.0] | Smart money cluster sell pressure |
| `pmkt_event_risk` | float | [0.0, 1.0] | Polymarket event risk score |
| `time_since_launch_hours` | float | [0.0, ∞) | Hours since token launch |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `hazard_score_raw` | float | Raw hazard score before calibration |
| `hazard_score_calibrated` | float | Calibrated probability [0.0, 1.0] |
| `is_emergency_exit` | bool | Whether to trigger emergency exit |
| `triggering_features` | list[str] | Features above threshold |
| `model_version` | str | Model version identifier |

## Implementation

### Core Module

```
analysis/survival_model.py
├── compute_hazard_score(features: dict) -> float
├── is_emergency_exit(score: float, threshold: float) -> bool
└── calibrate_hazard_score(raw: float, curve: list) -> float
```

### Calibration Loader

```
integration/models/hazard_calibrator.py
├── load_hazard_calibration(model_version) -> list[tuple]
├── save_hazard_calibration(curve, model_version)
└── get_default_calibration() -> list[tuple]
```

### Schema

```
strategy/schemas/hazard_score_schema.json
```

## Configuration

In `strategy/config/params_base.yaml`:

```yaml
hazard_model:
  # Feature weights
  weight_liquidity_drop: 3.2
  weight_top_holder_sell: 2.8
  weight_mint_auth: 1.5
  weight_cluster_pressure: 2.1
  weight_pmkt_event: 1.0
  
  # Model parameters
  sigmoid_k: 10.0
  sigmoid_x0: 0.5
  
  # Decision thresholds
  hazard_threshold: 0.65
  
  # Calibration
  model_version: "hazard_v1"
```

## Usage

```python
from analysis.survival_model import compute_hazard_score, is_emergency_exit

features = {
    'liquidity_drop_10s': 0.92,
    'top_holder_sell_ratio': 0.85,
    'mint_auth_exists': 1.0,
    'cluster_sell_pressure': 0.78,
    'pmkt_event_risk': 0.45,
    'time_since_launch_hours': 2.5
}

raw_score = compute_hazard_score(features)
calibrated = calibrate_hazard_score(raw_score)

if is_emergency_exit(calibrated, threshold=0.65):
    print("EMERGENCY EXIT TRIGGERED")
```

## Smoke Test

```bash
bash scripts/hazard_model_smoke.sh
```

Expected output:
```
[hazard_model_smoke] Starting hazard model smoke test...
[hazard_model_smoke] survival_model.py imports OK
[hazard_model_smoke] hazard_calibrator.py imports OK
[OK] hazard_score_schema.json exists
[OK] hazard_training_sample.json exists
[hazard_model_smoke] Crash score (0.812) > Survivor score (0.098): OK
[hazard_model_smoke] Emergency exit triggered for crash (score=0.812): OK
[hazard_model_smoke] Avg crash score: 0.785
[hazard_model_smoke] Avg survivor score: 0.112
[hazard_model_smoke] Training sample separation OK
[hazard_model_smoke] Schema validation OK
[OK] hazard_model_smoke
```

## Integration Points

1. **Position Sizing** — Higher hazard scores reduce position size
2. **Emergency Exit** — Scores above threshold trigger immediate exit
3. **Signal Enrichment** — Hazard fields added to all trade signals

## GREP Points

```bash
grep -n "compute_hazard_score" analysis/survival_model.py
grep -n "hazard_score_calibrated" strategy/schemas/hazard_score_schema.json
grep -n "hazard_threshold" strategy/config/params_base.yaml
grep -n "PR-ML.4" strategy/docs/overlay/PR_ML4_HAZARD_MODEL.md
grep -n "\[hazard_model_smoke\]" scripts/hazard_model_smoke.sh
```

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `analysis/survival_model.py` | Created | Core hazard scoring functions |
| `strategy/schemas/hazard_score_schema.json` | Created | Output schema |
| `integration/models/hazard_calibrator.py` | Created | Calibration loader |
| `integration/fixtures/ml/hazard_training_sample.json` | Created | Training data (70 trades) |
| `scripts/hazard_model_smoke.sh` | Created | Smoke test |
| `strategy/docs/overlay/PR_ML4_HAZARD_MODEL.md` | Created | This document |

## Backward Compatibility

- Pure functions with no side effects
- All new fields optional in existing pipelines
- Default `hazard_threshold=0.65` preserves existing behavior

## Future Enhancements

1. **Online Learning** — Update weights based on new crash data
2. **Feature Expansion** — Add holder distribution, volume spikes
3. **Time Decay** — Weight recent crashes more heavily
4. **Cluster-specific Weights** — Different weights per smart money cluster
