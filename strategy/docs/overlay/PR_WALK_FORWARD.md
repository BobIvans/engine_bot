# PR-D.1 Walk-Forward Backtest Harness

## Goal

Walk-forward backtesting is a technique that evaluates a trading strategy across multiple temporal windows to assess performance consistency and robustness. Unlike a single static backtest, walk-forward analysis:

- **Slices data into overlapping/non-overlapping time windows** (e.g., 1-day windows stepping by 1 day)
- **Runs independent simulations for each window** using the same strategy configuration
- **Aggregates results** to show how metrics vary across different time periods
- **Prevents look-ahead bias** by only using data within each window's boundaries

This harness is essential for validating that strategy performance is stable across different market conditions and time periods.

## CLI Usage

```bash
python3 -m integration.walk_forward \
  --trades <path> \
  --config <path> \
  --window-days <int> \
  --step-days <int> \
  --token-snapshot <path> \
  --wallet-profiles <path> \
  --out <path>
```

### Arguments

| Argument | Required | Type | Description |
|----------|----------|------|-------------|
| `--trades` | Yes | string | Path to trades JSONL file containing historical trades |
| `--config` | Yes | string | Path to strategy configuration YAML file |
| `--window-days` | Yes | int | Size of each walk-forward window in days (must be > 0) |
| `--step-days` | Yes | int | Step size between window starts in days (must be > 0) |
| `--token-snapshot` | Yes | string | Path to token snapshot CSV for price/state data |
| `--wallet-profiles` | Yes | string | Path to wallet profiles CSV for wallet metadata |
| `--out` | Yes | string | Output path for results JSON file |

### Success Output

On success, the harness writes results to `--out` and outputs a confirmation to stderr:

```
[walk_forward] OK ✅
```

### Error Output

Errors are written to stderr with `ERROR:` prefix and exit code 1.

## Output Schema

The output is written to `results_v1.json` with the following structure:

```json
{
  "schema_version": "results.v1",
  "title": "PR-D walk forward",
  "run": {
    "created_utc": "1970-01-01T00:00:00Z",
    "run_trace_id": "walk_forward"
  },
  "sweeps": [
    {
      "name": "walk_forward",
      "unit": "date_iso",
      "values": ["2024-01-01", "2024-01-02"],
      "rows": [
        {
          "window_start": "2024-01-01",
          "trade_count": 2,
          "pnl_total": 150.0,
          "win_rate": 0.75,
          ...
        },
        {
          "window_start": "2024-01-02",
          "trade_count": 1,
          "pnl_total": 75.0,
          "win_rate": 1.0,
          ...
        }
      ]
    }
  ],
  "notes": ["Deterministic walk-forward backtest; no external APIs."]
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Schema version identifier (`results.v1`) |
| `title` | string | Human-readable title for the results |
| `run.created_utc` | string | Timestamp of run in ISO format (fixed for determinism) |
| `run.run_trace_id` | string | Trace identifier (`walk_forward`) |
| `sweeps[].name` | string | Name of the sweep (`walk_forward`) |
| `sweeps[].unit` | string | Unit of analysis (`date_iso` for temporal windows) |
| `sweeps[].values` | array | List of window start dates in ISO format |
| `sweeps[].rows` | array | Simulation results for each window |
| `sweeps[].rows[].window_start` | string | ISO date of window start |
| `sweeps[].rows[].trade_count` | int | Number of trades in this window |
| `sweeps[].rows[].pnl_total` | float | Total P&L for this window |
| `sweeps[].rows[].win_rate` | float | Win rate (ratio of winning trades) |
| `notes` | array | Additional notes about the run |

## Configuration

The walk-forward harness uses the same strategy configuration format as other integration modules. See [`integration/fixtures/config/walk_forward.yaml`](../../integration/fixtures/config/walk_forward.yaml) for a minimal example.

### Required Config Fields

```yaml
version: "0.0"
strategy_name: "walk-forward-fixture"

run:
  timezone: "Europe/Riga"
  mode: "paper"

wallet_profile: {}

token_profile:
  gates: {}
  honeypot:
    enabled: false

signals: {}

risk: {}

execution: {}

# Strategy-specific parameters
min_edge_bps: 0
modes:
  default:
    tp_pct: 0.05
    sl_pct: -0.05
    hold_sec_max: 10
```

### Key Parameters

| Parameter | Description |
|-----------|-------------|
| `modes.default.tp_pct` | Take profit percentage (e.g., 0.05 = 5%) |
| `modes.default.sl_pct` | Stop loss percentage (e.g., -0.05 = -5%) |
| `modes.default.hold_sec_max` | Maximum hold time in seconds |
| `min_edge_bps` | Minimum edge in basis points to execute trade |

## Example

### Running with Fixture Data

```bash
python3 -m integration.walk_forward \
  --trades integration/fixtures/trades.walk_forward.jsonl \
  --config integration/fixtures/config/walk_forward.yaml \
  --window-days 1 \
  --step-days 1 \
  --token-snapshot integration/fixtures/token_snapshot.sim_preflight.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.sim_preflight.csv \
  --out /tmp/walk_forward_results.json
```

### Smoke Test

Run the smoke test to validate the harness:

```bash
./scripts/walk_forward_smoke.sh
```

Expected output:
```
[walk_forward_smoke] OK ✅
```

### Fixture Data

The test fixtures include:
- **Trades**: [`integration/fixtures/trades.walk_forward.jsonl`](../../integration/fixtures/trades.walk_forward.jsonl) - 4 trades across 2 days (Jan 1-2, 2024)
- **Config**: [`integration/fixtures/config/walk_forward.yaml`](../../integration/fixtures/config/walk_forward.yaml) - Minimal strategy config
- **Token Snapshot**: [`integration/fixtures/token_snapshot.sim_preflight.csv`](../../integration/fixtures/token_snapshot.sim_preflight.csv)
- **Wallet Profiles**: [`integration/fixtures/wallet_profiles.sim_preflight.csv`](../../integration/fixtures/wallet_profiles.sim_preflight.csv)

## Related Files

| File | Purpose |
|------|---------|
| [`integration/walk_forward.py`](../../integration/walk_forward.py) | Main implementation |
| [`scripts/walk_forward_smoke.sh`](../../scripts/walk_forward_smoke.sh) | Smoke test script |
| [`integration/sim_preflight.py`](../../integration/sim_preflight.py) | Simulation engine used per window |
| [`integration/token_snapshot_store.py`](../../integration/token_snapshot_store.py) | Token price/state data store |
| [`integration/wallet_profile_store.py`](../../integration/wallet_profile_store.py) | Wallet metadata store |
