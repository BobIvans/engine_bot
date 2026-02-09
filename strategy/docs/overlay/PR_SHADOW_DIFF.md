# PR-E.1 Paper vs Live Shadow Diff

## Goal

The **Deterministic Shadow Diff** feature compares paper simulation results against live execution to detect divergences in trading behavior. It enables:

- **Slippage detection**: Identify differences between simulated and actual fill prices
- **Fill rate analysis**: Compare fill success rates between paper and live environments
- **PnL drift tracking**: Monitor cumulative profit/loss deviations from expected performance
- **Signal-level granularity**: Per-signal comparison via `signal_id` or `trace_id`

This tooling is essential for validating that paper trading accurately predicts live trading outcomes, catching issues like API latency differences, order book slippage, or execution failures before they impact production.

## CLI Usage

Run the shadow diff tool from the project root:

```bash
python3 -m integration.shadow_diff \
    --paper <path-to-paper-trades.jsonl> \
    --live <path-to-live-trades.jsonl> \
    --out <path-to-output.json>
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--paper` | Yes | Path to paper simulation trades (JSONL format) |
| `--live` | Yes | Path to live execution trades (JSONL format) |
| `--out` | Yes | Path for output JSON results |

## Metrics

### Summary Metrics

| Metric | Description |
|--------|-------------|
| `rows_matched` | Number of trades matched by `signal_id` (inner join) |
| `fill_match_rate` | Proportion of trades where `filled` status matched between paper and live |
| `avg_entry_slippage_bps` | Average slippage at entry price, expressed in basis points (bps) |
| `fill_rate_divergence` | Difference in fill rates: `live_fill_rate - paper_fill_rate` |
| `total_pnl_drift_usd` | Cumulative PnL difference: `sum(live_pnl_usd - paper_pnl_usd)` |

### Per-Row Metrics

| Column | Description |
|--------|-------------|
| `signal_id` | Trade identifier (primary key for matching) |
| `paper_price` | Fill/price from paper simulation |
| `live_price` | Fill/price from live execution |
| `slippage_bps` | Entry slippage: `((live_price - paper_price) / paper_price) * 10000` |
| `paper_filled` | Boolean indicating if paper trade was filled |
| `live_filled` | Boolean indicating if live trade was filled |
| `fill_match` | Boolean: `paper_filled == live_filled` |
| `paper_pnl_usd` | PnL from paper simulation |
| `live_pnl_usd` | PnL from live execution |
| `pnl_drift_usd` | PnL difference: `live_pnl_usd - paper_pnl_usd` |

## Output Schema

The output follows the `diff_metrics.v1` schema:

```json
{
  "schema_version": "diff_metrics.v1",
  "title": "PR-E shadow diff",
  "run": {
    "created_utc": "2024-01-15T10:30:00Z"
  },
  "summary": {
    "rows_matched": 2,
    "fill_match_rate": 0.5,
    "avg_entry_slippage_bps": 50.0,
    "fill_rate_divergence": 0.1,
    "total_pnl_drift_usd": -5.25
  },
  "rows": [
    {
      "signal_id": "Sig1",
      "paper_price": 100.0,
      "live_price": 101.0,
      "slippage_bps": 100.0,
      "paper_filled": true,
      "live_filled": true,
      "fill_match": true,
      "paper_pnl_usd": 0.0,
      "live_pnl_usd": -1.0,
      "pnl_drift_usd": -1.0
    }
  ]
}
```

## Example

### Input Files

**Paper trades** (`paper.jsonl`):
```jsonl
{"signal_id": "Sig1", "side": "ENTER", "price": 100.0, "filled": true, "pnl_usd": 0.0}
{"signal_id": "Sig2", "side": "ENTER", "price": 200.0, "filled": true, "pnl_usd": 0.0}
```

**Live trades** (`live.jsonl`):
```jsonl
{"signal_id": "Sig1", "side": "ENTER", "price": 101.0, "filled": true, "pnl_usd": -1.0}
{"signal_id": "Sig2", "side": "ENTER", "price": 200.0, "filled": false, "pnl_usd": 0.0}
```

### Running the Tool

```bash
python3 -m integration.shadow_diff \
    --paper paper.jsonl \
    --live live.jsonl \
    --out diff_output.json
```

### Interpretation

- **Sig1**: Filled in both environments, but live price was 101 vs paper 100 (100 bps slippage)
- **Sig2**: Paper filled, but live did not fill (fill mismatch detected)

The summary shows:
- `rows_matched: 2` - both signals found in both files
- `fill_match_rate: 0.5` - only 1 of 2 trades had matching fill status
- `avg_entry_slippage_bps: 50.0` - average across matched trades
- `total_pnl_drift_usd: -1.0` - PnL deviation from paper expectations

## Related Files

| Path | Purpose |
|------|---------|
| [`integration/shadow_diff.py`](integration/shadow_diff.py) | Main implementation |
| [`scripts/shadow_diff_smoke.sh`](scripts/shadow_diff_smoke.sh) | Smoke test script |
| [`integration/fixtures/shadow_diff/paper.jsonl`](integration/fixtures/shadow_diff/paper.jsonl) | Paper fixture for testing |
| [`integration/fixtures/shadow_diff/live.jsonl`](integration/fixtures/shadow_diff/live.jsonl) | Live fixture for testing |
