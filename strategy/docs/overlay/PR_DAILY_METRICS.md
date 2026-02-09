# PR-7: Daily Metrics Aggregation

**Status:** Implemented  
**Schema:** `daily_metrics.v1`  
**Author:** Strategy Pack Team

## Overview

PR-7 introduces deterministic PnL aggregation into daily metrics. The `daily_metrics.v1` schema provides a comprehensive breakdown of trading performance including PnL, ROI, winrate, max drawdown, and fill rate with breakdowns by mode and tier.

## Key Features

- **Deterministic daily aggregation** — No randomness, no external calls
- **Offline computation** — Works without RPC/network access
- **Schema-based output** — Structured daily_metrics.v1 format
- **Breakdown support** — By mode and tier analysis

## daily_metrics.v1 Schema

```json
{
  "schema_version": "daily_metrics.v1",
  "days": [
    {
      "date_utc": "2026-01-05",
      "bankroll_usd_start": 10000.0,
      "bankroll_usd_end": 10050.0,
      "pnl_usd": 50.0,
      "roi": 0.005,
      "trades": 2,
      "wins": 1,
      "losses": 1,
      "winrate": 0.5,
      "max_drawdown": 0.01,
      "fill_rate": 0.5,
      "exit_reason_counts": {"TP":1,"SL":1,"TIME":0},
      "skipped_by_reason": {"missing_snapshot":0,"missing_wallet_profile":0,"ev_below_threshold":0}
    }
  ],
  "totals": {
    "days": 1,
    "pnl_usd": 50.0,
    "roi": 0.005,
    "trades": 2,
    "winrate": 0.5,
    "max_drawdown": 0.01,
    "fill_rate": 0.5
  },
  "breakdown": {
    "by_mode": { "U": {"trades":2,"pnl_usd":50.0,"roi":0.005} },
    "by_tier": { "tier1": {"trades":2,"pnl_usd":50.0,"roi":0.005} }
  }
}
```

## Usage

```bash
python3 -m integration.paper_pipeline \
  --dry-run \
  --summary-json \
  --sim-preflight \
  --daily-metrics \
  --config integration/fixtures/config/daily_metrics.yaml \
  --trades-jsonl integration/fixtures/trades.daily_metrics.jsonl \
  --token-snapshot integration/fixtures/token_snapshot.sim_preflight.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.sim_preflight.csv
```

## Max Drawdown (MVP)

**MVP Limitation:** `max_drawdown` is calculated as `0.0` when no equity curve is available. Future iterations will implement full equity curve tracking for accurate drawdown calculation.

## Error Handling

- `--daily-metrics` requires `--sim-preflight` (RC=2, message: `ERROR: daily_metrics_requires_sim_metrics`)
- All errors written to stderr, stdout preserved for JSON output

## Smoke Tests

```bash
bash scripts/daily_metrics_smoke.sh        # Positive cases
bash scripts/daily_metrics_negative_smoke.sh  # Error cases
```

## GREP Points

- `daily_metrics.v1`
- `max_drawdown`
- `Deterministic daily aggregation`
- `PR-7`
