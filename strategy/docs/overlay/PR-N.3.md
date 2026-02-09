# PR-N.3 — Calibrated Inference Adapter

**Status:** Implemented  
**Date:** 2024-01-15  
**Owner:** ML Pipeline Team

## Overview

Connects the calibration model (Platt / Isotonic from PR-N.1) to runtime prediction, converting raw model scores into honest probabilities `p_model` for correct EV calculation.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Base Model     │────▶│  CalibratedPredictor │────▶│  Calibrated     │
│  (raw scores)   │     │  (calibration_adapter │     │  Probability    │
│                 │     │   .py)                │     │  p_model [0..1] │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
```

## Components

### 1. `strategy/calibration_adapter.py`

Main adapter class that wraps base models with calibration:

```python
from strategy.calibration_adapter import CalibratedPredictor, create_calibrated_predictor

# Direct instantiation
calibrator = load_calibrator({"method": "platt", "params": {"a": 1.0, "b": 0.0}})
predictor = CalibratedPredictor(base_model, calibrator)
p_calibrated = predictor.predict_proba(features_dict)

# Factory with file loading
predictor = create_calibrated_predictor(
    base_model,
    calibration_path="calibration_config.json"
)
```

**Key Methods:**

- `predict_proba(x: Dict[str, Any]) -> float`: Returns calibrated probability
- `predict_proba_batch(batch: list[Dict]) -> list[float]`: Batch inference

### 2. `strategy/calibration_loader.py`

Loads calibrators from config dictionaries (pure function, no I/O):

```python
from strategy.calibration_loader import load_calibrator

# Platt scaling
calibrator = load_calibrator({
    "method": "platt",
    "params": {"a": 1.0, "b": 0.0}
})
# P(y=1|x) = 1 / (1 + exp(-(a*x + b)))

# Identity (no calibration)
calibrator = load_calibrator({"method": "identity"})
```

### 3. Fixtures

Located in `integration/fixtures/calibration/`:

- `platt_fixture.json`: Standard Platt calibrator (a=1.0, b=0.0)
- `mock_raw_scores.jsonl`: Sample raw scores for testing
- `expected_calibrated_probs.json`: Expected outputs for verification

## Integration Points

### Model Inference (`integration/model_inference.py`)

Replace direct model calls with calibrated predictor:

```python
# Before
p_raw = model.predict_proba(features)

# After
calibrated_predictor = create_calibrated_predictor(
    model,
    calibration_path=CALIBRATION_PATH
)
p_calibrated = calibrated_predictor.predict_proba(features)
```

### Signal Engine (`strategy/signal_engine.py`)

The `decide_entry()` function already accepts `p_model` parameter:

```python
signal = decide_entry(
    trade,
    snapshot,
    wallet_profile,
    cfg,
    p_model=p_calibrated,  # Use calibrated probability
    risk_regime=regime
)
```

## Hard Rules

1. **Fallback Behavior**: If calibrator file is missing/invalid, returns raw score + warning
2. **Output Range**: Always returns float in [0, 1] range
3. **Offline**: No network calls during inference
4. **Deterministic**: Same input always produces same output
5. **Monotonicity**: Calibration preserves input ordering

## Calibration Methods

### Platt Scaling

Formula: `P(y=1|x) = 1 / (1 + exp(-(a*x + b)))`

- `a`: Scale parameter (positive = preserves ordering)
- `b`: Bias parameter (shifts decision boundary)

### Identity

Returns raw score unchanged (for comparison/no-calibration scenarios)

## Testing

Run smoke test:

```bash
bash scripts/calibration_adapter_smoke.sh
```

Expected output:

```
[overlay_lint] running calibration adapter smoke...
[calibration_adapter_smoke] OK
```

## Related PRs

- **PR-N.1**: Probability Calibration Module (base calibration logic)
- **PR-N.2**: Model Inference Interface
- **PR-S.1**: Signal Engine v1 (uses p_model)

## GREP Points

```bash
grep -n "PR-N.3" strategy/docs/overlay/PR-N.3.md
grep -n "CalibratedPredictor" strategy/calibration_adapter.py
grep -n "load_calibrator" strategy/calibration_loader.py
grep -n "\[calibration_adapter_smoke\] OK" scripts/calibration_adapter_smoke.sh
```
