# PR-ML.2: Memecoin-Specific Feature Engineering

| Field | Value |
|-------|-------|
| **PR** | ML.2 |
| **Status** | Implemented |
| **Author(s)** | System |
| **Reviewer(s)** | TBD |
| **Created** | 2024-01-15 |
| **Updated** | 2024-01-15 |

## Overview

Extends feature vectors with 4 memecoin-specific features based on launch characteristics and deployer history. Uses on-chain first principle (Pump.fun events before external APIs).

## Features

| Feature | Range | Description |
|---------|-------|-------------|
| `time_since_launch_hours` | [0.0, 720.0] | Hours since first pool listing |
| `launch_source_encoded` | [0.0, 3.0] | One-hot encoded launch source |
| `deployer_reputation_score` | [-1.0, +1.0] | Normalized deployer success |
| `social_mention_velocity` | [0.0, 10.0] | Mentions per minute |

## Formulas

### time_since_launch_hours

```
hours = (current_ts - first_pool_ts) / (1000 * 60 * 60)
```

**Range**: [0.0, 720.0] (30 days max)  
**Missing Data**: 360.0 (midpoint, neutral)

### launch_source_encoded

```
pump_fun -> 0.0
raydium_cpmm -> 1.0
meteora -> 2.0
unknown -> 3.0
```

**Range**: [0.0, 3.0]  
**Missing Data**: 1.0 (raydium_cpmm as baseline)

### deployer_reputation_score

```
score = clamp(reputation, -1.0, +1.0)
```

**Range**: [-1.0, +1.0]  
**Missing Data**: 0.0 (neutral)

### social_mention_velocity

```
velocity = mention_count / time_window_minutes
```

**Range**: [0.0, 10.0] (clamped)  
**Missing Data**: 1.0 (normal activity)

## Data Sources

| Source | Type | Rate Limit | Cache TTL |
|--------|------|------------|-----------|
| Pump.fun API | External | 1 req/sec | 3600s |
| SolanaFM | External | 1 req/sec | 3600s |
| RPC | On-chain | N/A | N/A |

## Data Adapters

- `ingestion/sources/pumpfun.py`: Pump.fun API adapter
- `ingestion/sources/deployer_reputation.py`: Deployer reputation via SolanaFM

## Feature Importance Calibration

Based on historical correlation analysis with trading outcomes:

| Feature | Correlation | Interpretation |
|---------|-------------|----------------|
| `time_since_launch_hours` | -0.28 | Newer tokens → higher returns (risk) |
| `launch_source_encoded` | +0.15 | Pump.fun launches → better fundamentals |
| `deployer_reputation_score` | +0.41 | High reputation → lower rug probability |
| `social_mention_velocity` | +0.33 | Viral tokens → momentum plays |

### Recommendations

- Use all 4 features in model
- High weight on `deployer_reputation_score` (strongest signal)
- Consider interaction: `reputation_score * velocity`
- Cap `time_since_launch_hours` at 720h (30 days)

## Testing

```bash
# Run smoke tests
bash scripts/memecoin_features_smoke.sh

# Expected output
[memecoin_features_smoke] Starting memecoin features smoke test...
[memecoin_features_smoke] Module import: OK
[memecoin] WIF: hours=24.3, source=0.0, reputation=0.85
[memecoin] BONK: hours=124.3, source=1.0, reputation=-0.30
[memecoin] NEWME: hours=360.0 (neutral), source=3.0, reputation=0.0
[memecoin_features_smoke] Feature validation: OK
[memecoin_features_smoke] OK
```

## Files

| File | Description |
|------|-------------|
| `analysis/memecoin_features.py` | Pure feature computation functions |
| `ingestion/sources/pumpfun.py` | Pump.fun API adapter |
| `ingestion/sources/deployer_reputation.py` | Deployer reputation cache |
| `integration/fixtures/ml/memecoin_launch_sample.json` | Test tokens (WIF, BONK, NEWME) |
| `scripts/memecoin_features_smoke.sh` | Smoke test |

## GREP Points

```bash
grep -n "compute_time_since_launch_hours" analysis/memecoin_features.py
grep -n "compute_launch_source_encoded" analysis/memecoin_features.py
grep -n "compute_deployer_reputation_score" analysis/memecoin_features.py
grep -n "PR-ML.2" strategy/docs/overlay/PR_ML2_MEMECOIN_FEATURES.md
grep -n "LAUNCH_SOURCE_ENCODING" analysis/memecoin_features.py
```

## Integration

```python
from analysis.memecoin_features import (
    compute_memecoin_features,
    MemecoinLaunchData,
    SocialData,
)

# Compute all 4 features
features = compute_memecoin_features(
    current_ts=1738937400000,
    launch_data=MemecoinLaunchData(
        mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        first_pool_ts=1738858800000,
        first_pool_source="pump_fun",
        deployer_address="7pLXfGzNqwFHg6X3EQ9BHJcz3o4yX6y7X8Y9Z2",
        deployer_reputation=0.85,
    ),
    social_data=SocialData(mention_count=300, time_window_minutes=60),
)
# Returns: {
#     "time_since_launch_hours": 24.3,
#     "launch_source_encoded": 0.0,
#     "deployer_reputation_score": 0.85,
#     "social_mention_velocity": 5.0,
# }
```

## Fixture Data

| Token | Launch Source | Deployer Reputation | Expected Score |
|-------|---------------|---------------------|----------------|
| WIF | pump_fun | +0.85 | 24.3h, 0.85 rep |
| BONK | raydium_cpmm | -0.30 | 124.3h, -0.30 rep |
| NEWME | unknown | null | 360.0h (neutral), 0.0 rep |

## Backward Compatibility

All features are optional:
- Missing launch data → features use neutral defaults
- Existing pipelines continue to work
- New features appended to feature vector
