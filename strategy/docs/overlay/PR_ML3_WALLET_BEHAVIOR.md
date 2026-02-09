# PR-ML.3: Wallet Behavior Features

**Status:** Implemented  
**Date:** 2024-02-09  
**Owner:** ML Platform Team

## Overview

PR-ML.3 adds behavioral pattern features that describe wallet trading behavior based on historical trades. These features capture:

- **Winning streaks**: How many consecutive profitable trades a wallet has
- **Hold time patterns**: How the wallet's hold time compares to the population
- **DEX preferences**: Concentration of trading activity on specific DEXs
- **Cluster leadership**: Wallet's role in co-trading clusters (PR-WD.4)

## Feature Specifications

### 1. `n_consecutive_wins`

**Description:** Number of consecutive winning trades before the current trade.

**Formula:**
```
Let W = {t | t.wallet = wallet_addr AND t.ts < current_ts}
Sorted by ts descending, take top 20

streak = 0
For each trade t in W:
    if is_profitable(t):
        streak += 1
    else:
        break

n_consecutive_wins = min(streak, 20)
```

**Profitability check:**
```
is_profitable(t) = (t.exit_price_usd > t.entry_price_usd * 1.005)
```
(0.5% threshold accounts for trading fees)

**Range:** `[0, 20]` (capped at 20 for robustness)

**Missing data handling:**
- No trade history → `0`

### 2. `avg_hold_time_percentile`

**Description:** Percentile of the wallet's median hold time relative to the population.

**Formula:**
```
Let H = {p.median_hold_sec | p in population_profiles AND p.median_hold_sec > 0}
Sorted H ascending: h_1 <= h_2 <= ... <= h_n

wallet_hold = wallet_profile.median_hold_sec

rank = count of h_i where h_i <= wallet_hold
percentile = (rank / n) * 100
```

**Range:** `[0.0, 100.0]`

**Missing data handling:**
- No hold time data → `50.0` (population median)

### 3. `preferred_dex_concentration`

**Description:** Fraction of trades on the wallet's most-used DEX.

**Formula:**
```
Let T = {t | t.wallet = wallet_addr} [-50 most recent]
For each t in T:
    count[dex] += 1

max_count = max(count.values())
concentration = max_count / |T|
```

**Range:** `[0.0, 1.0]`
- `1.0` = All trades on a single DEX
- Lower values = More diversified DEX usage

**Missing data handling:**
- No trades → `0.5` (neutral value)

### 4. `co_trade_cluster_leader_score`

**Description:** Leadership score from co-trading clusters (PR-WD.4).

**Source:** Pre-computed from PR-WD.4 clustering output.

**Range:** `[0.0, 1.0]`
- `1.0` = Strong cluster leader
- `0.0` = Cluster follower

**Missing data handling:**
- No cluster assignment → `0.5` (neutral value)

## Aggregation Windows

| Feature | Window | Notes |
|---------|--------|-------|
| `n_consecutive_wins` | 20 trades | Reversed order (most recent first) |
| `preferred_dex_concentration` | 50 trades | Most recent |
| `avg_hold_time_percentile` | Population | Uses full population baseline |

## Population Baseline Strategy

For deterministic behavior:

1. **Daily snapshot:** Population baseline is fixed daily via `data/wallets/population_baseline_{date}.parquet`
2. **First run of day:** Generate new baseline if not exists
3. **CI/Testing:** Use deterministic fixture `integration/fixtures/ml/wallet_profiles_behavior_sample.parquet`

## Implementation

### Pure Functions

All feature computation is done via pure functions with no side effects:

```python
from analysis.wallet_behavior_features import (
    compute_n_consecutive_wins,
    compute_avg_hold_time_percentile,
    compute_preferred_dex_concentration,
    compute_cluster_leader_score,
)
```

### Integration

```python
from features.trade_features import build_features_with_behavior

features = build_features_with_behavior(
    trade=trade,
    snapshot=snapshot,
    wallet_profile=wallet_profile,
    trades_history=historical_trades,
    population_profiles=population_profiles,
)
```

## Schema Extension

The feature vector schema (`strategy/schemas/feature_vector_schema.json`) is extended with:

```json
{
  "n_consecutive_wins": {
    "type": "integer",
    "minimum": 0,
    "maximum": 20,
    "description": "PR-ML.3: Number of consecutive winning trades (capped at 20)"
  },
  "avg_hold_time_percentile": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 100.0,
    "description": "PR-ML.3: Percentile of median hold time vs population"
  },
  "preferred_dex_concentration": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 1.0,
    "description": "PR-ML.3: DEX activity concentration (1.0 = single DEX)"
  },
  "co_trade_cluster_leader_score": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 1.0,
    "description": "PR-ML.3: Leadership score from co-trade clusters"
  }
}
```

## Test Fixtures

### Trades (`integration/fixtures/ml/wallet_trades_behavior_sample.csv`)

| Wallet | Pattern | Trades | DEX Distribution |
|--------|---------|-------|------------------|
| W1 | Leader | 10 | 95% Raydium, 5% Orca |
| W2 | Follower | 7 | 60% distributed |
| W3 | New | 1 | Raydium |

### Profiles (`integration/fixtures/ml/wallet_profiles_behavior_sample.csv`)

| Wallet | median_hold_sec | leader_score | cluster_label |
|--------|-----------------|--------------|---------------|
| W1 | 120 | 0.92 | 0 |
| W2 | 45 | 0.35 | 1 |
| W3 | null | null | null |

### Expected Values

| Wallet | n_consecutive_wins | avg_hold_percentile | dex_conc | leader_score |
|--------|-------------------|---------------------|----------|--------------|
| W1 | 8 | 92.0 | 0.95 | 0.92 |
| W2 | 2 | 50.0 | 0.60 | 0.35 |
| W3 | 0 | 50.0 | 0.50 | 0.50 |

## Smoke Test

Run validation:

```bash
bash scripts/wallet_behavior_smoke.sh
```

Expected output:
```
[overlay_lint] running wallet_behavior smoke...
[wallet_behavior] tested 3 wallets
[wallet_behavior_smoke] validated wallet behavior features against schema
[wallet_behavior_smoke] OK
```

## Related PRs

- **PR-WD.4**: Co-trading cluster detection (source of `leader_score`)
- **PR-ML.2**: Core feature pipeline
- **PR-ML.4**: Hazard scoring (depends on these features)

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-02-09 | Initial implementation |
