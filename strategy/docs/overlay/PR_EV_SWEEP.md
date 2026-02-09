# PR-9: EV Calibration / Threshold Sweep

## Overview

PR-9 adds an offline "threshold sweep" for the +EV gate (`min_edge_bps`). This tool allows systematic analysis of how different edge thresholds affect strategy performance.

## Key Concepts

### threshold sweep

A systematic analysis that runs the simulation pipeline across multiple `min_edge_bps` threshold values to understand how sensitivity to edge affects:
- Position count (entries)
- Win rate
- ROI
- PnL distribution

### min_edge_bps

The minimum edge threshold (in basis points) that a trade must have to be entered. Lower thresholds = more trades accepted. Higher thresholds = stricter filtering.

### results.v1

The JSON schema used for sweep results, containing:
- Schema version identifier
- Run metadata (timestamp, trace ID, fixture info)
- Sweep configuration (name, unit, values tested)
- Per-threshold simulation metrics
- Determinism notes

## Implementation

### Core Module

[`integration/ev_sweep.py`](../../../integration/ev_sweep.py) provides:
- `parse_thresholds(s: str) -> list[int]`: Parse comma-separated threshold values
- `run_ev_sweep(thresholds_bps, inputs, cfg) -> dict`: Execute sweep and return results
- `write_results_atomic(path, obj) -> None`: Atomic file write with temp swap

### Determinism Guarantees

- **No network calls**: All data loaded from local fixtures
- **No randomness**: All calculations are deterministic
- **No time.now**: Fixed timestamp (`1970-01-01T00:00:00Z`) for reproducibility
- **stdout empty**: All output goes to stderr or result file

### Results Schema (results.v1)

```json
{
  "schema_version": "results.v1",
  "title": "PR-9 ev sweep",
  "run": {
    "created_utc": "1970-01-01T00:00:00Z",
    "run_trace_id": "ev_sweep",
    "fixture": {...}
  },
  "sweeps": [
    {
      "name": "min_edge_bps",
      "unit": "bps",
      "values": [0, 50, 100],
      "rows": [
        {"value": 0, "sim_metrics": {...}},
        {"value": 50, "sim_metrics": {...}},
        {"value": 100, "sim_metrics": {...}}
      ]
    }
  ],
  "notes": ["Deterministic offline sweep; no external APIs."]
}
```

## Fixtures

### Configuration

- [`integration/fixtures/config/ev_sweep.yaml`](../../../integration/fixtures/config/ev_sweep.yaml): Strategy configuration with mode settings

### Trade Data

- [`integration/fixtures/trades.ev_sweep.jsonl`](../../../integration/fixtures/trades.ev_sweep.jsonl): 3 trades (high/medium/low edge) with ticks

### Reference Data

- [`integration/fixtures/token_snapshot.ev_sweep.csv`](../../../integration/fixtures/token_snapshot.ev_sweep.csv): Token snapshots for mints
- [`integration/fixtures/wallet_profiles.ev_sweep.csv`](../../../integration/fixtures/wallet_profiles.ev_sweep.csv): Wallet profiles with win rates

### Expected Results

- [`integration/fixtures/expected_ev_sweep_results.json`](../../../integration/fixtures/expected_ev_sweep_results.json): Expected sweep output for validation

## Usage

```bash
python3 -m integration.ev_sweep \
  --config integration/fixtures/config/ev_sweep.yaml \
  --allowlist strategy/wallet_allowlist.yaml \
  --token-snapshot integration/fixtures/token_snapshot.ev_sweep.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.ev_sweep.csv \
  --trades-jsonl integration/fixtures/trades.ev_sweep.jsonl \
  --thresholds-bps "0,50,100" \
  --out /tmp/results_v1.json
```

## Smoke Test

Run the smoke test to verify the sweep implementation:

```bash
bash scripts/ev_sweep_smoke.sh
```

This validates:
1. stdout is empty
2. Output file exists and is non-empty
3. Valid JSON output
4. schema_version == "results.v1"
5. sweeps[0].name == "min_edge_bps"
6. sweeps[0].values == [0,50,100]
7. Expected entries: 3 at 0 bps, 2 at 50 bps, 1 at 100 bps

## Integration

The sweep tool is integrated into the overlay lint pipeline:

```bash
bash scripts/overlay_lint.sh
```

This runs the EV sweep smoke test alongside other validation checks.

## Edge Calculation

The edge is calculated as:

```
edge_bps = int(round(gross_edge_pct * 10_000)) - costs_bps
gross_edge_pct = win_p * tp_pct - (1 - win_p) * sl_pct
```

Where:
- `win_p`: Wallet win rate (30-day)
- `tp_pct`: Take profit percentage (from mode config)
- `sl_pct`: Stop loss percentage (from mode config)
- `costs_bps`: Token spread in basis points

## Notes

- Deterministic offline sweep; no external APIs
- All results are reproducible given the same inputs
- The sweep tool is designed for calibration and sensitivity analysis
- Can be used to find optimal `min_edge_bps` settings for the strategy
