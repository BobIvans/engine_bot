# PR-7: PnL Aggregation + daily_metrics.v1 — Plan

## Goal
Добавить детерминированную агрегацию результатов симуляции в дневные метрики.

## Files to Create/Modify

### NEW Files
| File | Purpose |
|------|---------|
| `integration/pnl_aggregator.py` | Core aggregation logic |
| `scripts/daily_metrics_smoke.sh` | Positive smoke test |
| `scripts/daily_metrics_negative_smoke.sh` | Negative smoke test |
| `integration/fixtures/trades.daily_metrics.jsonl` | Test fixture |
| `integration/fixtures/config/daily_metrics.yaml` | Test config |
| `strategy/docs/overlay/PR_DAILY_METRICS.md` | Documentation |

### MOD Files
| File | Changes |
|------|---------|
| `integration/paper_pipeline.py` | Add `--daily-metrics` flag |
| `scripts/overlay_lint.sh` | Add daily_metrics smoke calls |
| `scripts/docs_smoke.sh` | Add grep tokens check |
| `strategy/docs/overlay/SPRINTS.md` | Add PR-7 reference |

## daily_metrics.v1 Schema

```json
{
  "daily_metrics": {
    "schema_version": "daily_metrics.v1",
    "days": [
      {
        "date_utc": "YYYY-MM-DD",
        "bankroll_usd_start": float,
        "bankroll_usd_end": float,
        "pnl_usd": float,
        "roi": float,
        "trades": int,
        "wins": int,
        "losses": int,
        "winrate": float,
        "max_drawdown": float,
        "fill_rate": float,
        "exit_reason_counts": {"TP": int, "SL": int, ...},
        "skipped_by_reason": {"reason": int, ...}
      }
    ],
    "totals": {
      "days": int,
      "pnl_usd": float,
      "roi": float,
      "trades": int,
      "winrate": float,
      "max_drawdown": float,
      "fill_rate": float
    },
    "breakdown": {
      "by_mode": {"mode": {"trades": int, "pnl_usd": float, "roi": float}},
      "by_tier": {"tier": {"trades": int, "pnl_usd": float, "roi": float}}
    }
  }
}
```

## Implementation Steps

### Step 1: integration/pnl_aggregator.py
```python
def aggregate_daily_metrics(summary: dict, cfg: dict) -> dict:
    """
    Input: summary with sim_metrics (positions_closed, roi_total, etc.)
    Output: daily_metrics.v1 dict
    """
    # MVP: max_drawdown = 0.0 if no equity curve
    # Deterministic, no external calls
```

### Step 2: Test Fixtures
- `trades.daily_metrics.jsonl` — 2 trades (1 win, 1 loss)
- `config/daily_metrics.yaml` — minimal valid config

### Step 3: Paper Pipeline Integration
- Add `--daily-metrics` bool flag
- Require `--sim-preflight` when `--daily-metrics` enabled
- Add `daily_metrics` to summary output

### Step 4: Smoke Tests
- `daily_metrics_smoke.sh` — positive case
- `daily_metrics_negative_smoke.sh` — error cases

### Step 5: Documentation
- PR_DAILY_METRICS.md with grep tokens

## Hard Rules
- ✅ Offline, deterministic (no RPC, no random, no now())
- ✅ stdout-contract: `--summary-json` = 1 line only
- ✅ New layer optional via `--daily-metrics` flag
- ✅ Oldsmokes stay green

## GREP Points
```bash
grep -n "daily-metrics" integration/paper_pipeline.py
grep -n "\"daily_metrics\"" integration/paper_pipeline.py
grep -n "def aggregate_daily_metrics" integration/pnl_aggregator.py
grep -n "\\[daily_metrics_smoke\\] OK ✅" scripts/daily_metrics_smoke.sh
grep -n "running daily metrics smoke" scripts/overlay_lint.sh
```

## Verification
```bash
bash scripts/daily_metrics_smoke.sh
bash scripts/daily_metrics_negative_smoke.sh
bash scripts/overlay_lint.sh
```
