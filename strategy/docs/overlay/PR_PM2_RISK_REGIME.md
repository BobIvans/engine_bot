# PR-PM.2 Risk Regime Computation

## Overview
Computes scalar `risk_regime` [-1.0..+1.0] from Polymarket snapshots.

## Formulas

### Market Bullishness Classification
- Bullish keywords: "BTC >", "Bitcoin exceed", "Crypto adoption", etc.
- Bearish keywords: "crash", "drop below", etc.
- `bullish_score = p_yes` for bullish, `1.0 - p_yes` for bearish

### Crypto-Relevance Weighting
| Market Type | Relevance |
|-------------|-----------|
| Crypto (BTC/ETH) | 1.0 |
| Macro (S&P 500) | 0.6 |
| Other | 0.2 |

### Volume Normalization
`volume_norm = (volume - min_vol) / (max_vol - min_vol)`

### Weighted Aggregate
`weighted_sum += (bullish_score - 0.5) * relevance * (0.7 + 0.3 * volume_norm)`

### Tanh Normalization
`risk_regime = tanh(2.0 * weighted_sum)` → maps to [-1.0, +1.0]

## Confidence
`confidence = abs(risk_regime)`

## CLI Usage
```bash
python3 -m ingestion.pipelines.regime_pipeline \
    --input polymarket_snapshots.parquet \
    --output regime_timeline.parquet \
    --ts-override=1738945200000 \
    --dry-run \
    --summary-json
```
