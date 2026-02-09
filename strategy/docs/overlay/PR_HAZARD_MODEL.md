# PR-Z.4 — Exit Hazard Prediction Model (Survival Analysis for 60s Crash Probability)

**Status:** In Progress  
**Owner:** Strategy Team  
**Created:** 2024-02-08

## Overview

This PR implements an offline-trained survival model for predicting token crash probability within 60 seconds after entry (`P(exit_next_60s)`). The model uses volume spikes, smart money exits, and liquidity drain as predictors.

## Goals

1. Predict probability of token crash within 60 seconds of entry
2. Integrate with exit logic for aggressive exits (chain reaction) and dynamic SL tightening
3. Use only offline-trained coefficients (no online learning in runtime)
4. Provide optional hazard scoring that can be enabled/disabled per run

## Model Specification

### Features

| Feature | Description | Expected Range |
|---------|-------------|----------------|
| `volume_spike_15s_z` | z-score of 15s volume relative to 5m average | -3.0 .. +5.0 |
| `smart_money_exits_30s` | Number of Tier-1 wallet exits in 30s | 0 .. 10 |
| `liquidity_drain_60s_pct` | Pool liquidity drain percentage over 60s | -50.0 .. +10.0 |
| `price_impact_15s_bps` | Price impact in basis points over 15s | -500 .. +2000 |

### Inference Formula

```
logit = β0 + β1·volume_spike_15s_z + β2·smart_money_exits_30s + β3·liquidity_drain_60s_pct + β4·price_impact_15s_bps
hazard_score = 1 / (1 + exp(-logit))
```

### Fixed Coefficients

```json
{
  "beta0": -1.2,
  "beta1": 0.35,
  "beta2": 0.8,
  "beta3": 0.04,
  "beta4": 0.0015
}
```

## Architecture

```
token_snapshot + wallet_profile
        ↓
integration/hazard_stage.py (optional, --enable-hazard-model)
        ↓
strategy/survival_model.py (pure logic)
        ↓
hazard_score [0.0, 1.0]
        ↓
ExitContext (for exits.py)
```

## Components

### 1. Pure Logic (`strategy/survival_model.py`)

```python
def predict_exit_hazard(features: dict) -> Tuple[float, Optional[str]]:
    """
    Predict P(exit_next_60s).
    
    Returns:
        (hazard_score: float, error_message: Optional[str])
        - hazard_score ∈ [0.0, 1.0]
        - error_message is None on success, or rejection reason on failure
    """
```

### 2. Pipeline Stage (`integration/hazard_stage.py`)

- CLI flag: `--enable-hazard-model` (store_true)
- Config: `--hazard-threshold` (default: 0.35)
- Metrics: `hazard_score_avg`, `hazard_score_max`, `hazard_triggered_count`

### 3. Fixtures (`integration/fixtures/hazard/`)

- `features_sample.jsonl`: 5 test records (3 valid, 2 invalid)
- `expected_hazard_scores.jsonl`: Expected outputs
- `survival_coefficients.json`: Fixed coefficients

## Integration

### Exit Logic (`strategy/exits.py`)

```python
if hazard_score > config.hazard_threshold:
    # Trigger aggressive exit (chain reaction)
    trigger_aggressive_exit(trade)
```

### Pipeline Integration (`integration/paper_pipeline.py`)

```
feature_wiring_stage → hazard_stage → decision_stage
```

## Configuration

In `config/runtime_schema.py`:

```python
hazard_threshold: float = Field(default=0.35, ge=0.1, le=0.7)
```

## Hard Rules

| Rule | Description |
|------|-------------|
| Offline coefficients only | No online learning in runtime |
| Feature validation | Out-of-range → rejection + 0.5 score |
| Optional | Disabled by default, enabled via flag |
| Deterministic | Same inputs → same outputs |

## Smoke Test

```bash
bash scripts/hazard_smoke.sh
```

Expected output:
```
[overlay_lint] running hazard smoke...
[hazard_smoke] hazard_score_avg: 0.364
[hazard_smoke] hazard_triggered_count: 2
[hazard_smoke] invalid_features_count: 2
[hazard_smoke] OK
```

## GREP Points

```bash
grep -n "def predict_exit_hazard" strategy/survival_model.py    # Line ~50
grep -n "survival_coefficients.json" strategy/survival_model.py  # Line ~25
grep -n "hazard_score_avg" integration/hazard_stage.py          # Line ~30
grep -n "REJECT_HAZARD_FEATURES_INVALID" integration/reject_reasons.py  # (to be added)
grep -n "PR-Z.4" strategy/docs/overlay/PR_HAZARD_MODEL.md       # Line 1
grep -n "\[hazard_smoke\] OK" scripts/hazard_smoke.sh           # Line ~60
```
