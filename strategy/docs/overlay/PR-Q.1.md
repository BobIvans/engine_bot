# PR-Q.1 — Stats Feedback Loop (Auto-update Params)

**Status:** Implemented  
**Date:** 2024-01-15  
**Owner:** ML Pipeline Team

## Overview

Offline script that analyzes daily_metrics and updates dynamic parameters in `params_base.yaml` using EWMA smoothing, allowing the +EV formula to adapt to changing market conditions.

## Architecture

```
┌─────────────────────────┐
│  Daily Metrics Store   │
│  (trades.daily_       │
│   metrics.jsonl)       │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  update_params.py       │
│  - Load recent trades   │
│  - Group by mode (U/S)  │
│  - Compute stats        │
│  - Apply EWMA           │
│  - Update params        │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  params_base.yaml       │
│  - payoff_mu_win       │
│  - payoff_mu_loss      │
└─────────────────────────┘
```

## Usage

```bash
# Basic usage
python strategy/optimization/update_params.py \
    --metrics data/daily_metrics.jsonl \
    --config strategy/config/params_base.yaml \
    --output /tmp/params_base_updated.yaml

# With summary JSON (stdout)
python strategy/optimization/update_params.py \
    --metrics data/daily_metrics.jsonl \
    --config strategy/config/params_base.yaml \
    --output /tmp/params_base_updated.yaml \
    --summary-json

# Dry run (print to stdout)
python strategy/optimization/update_params.py \
    --metrics data/daily_metrics.jsonl \
    --config strategy/config/params_base.yaml \
    --dry-run
```

## Components

### `strategy/optimization/update_params.py`

Main update script with:

- **Load Configuration**: Reads `auto_update` section from params_base.yaml
- **Load Metrics**: Reads recent trades from JSONL
- **Compute Stats**: Groups by mode, calculates winrate, avg win/loss %
- **Apply EWMA**: Smoothed updates: `new = α * target + (1-α) * current`
- **Apply Bounds**: Clamps values to configurable limits
- **Atomic Save**: Writes to temp file, then renames

**Key Classes/Functions:**

```python
from strategy.optimization.update_params import (
    UpdateConfig,    # Configuration dataclass
    ModeStats,       # Per-mode statistics
    compute_mode_stats,  # Calculate stats from trades
    apply_ewma,      # EWMA smoothing
    clamp_value,     # Bound checking
    load_config,     # Load from YAML
)

# Apply EWMA smoothing
new_value = apply_ewma(current=0.04, new=0.05, alpha=0.15)

# Clamp to bounds
bounded = clamp_value(0.5, [0.01, 0.25])
```

## Configuration

Added to `strategy/config/params_base.yaml`:

```yaml
# PR-Q.1: Stats Feedback Loop - Auto-update configuration
auto_update:
  enabled: true              # Enable/disable auto-update
  min_days_required: 7       # Min trades per mode to trigger update
  ewma_alpha: 0.15           # EWMA smoothing factor (0-1)
  bounds:
    mu_win: [0.01, 0.25]     # Bounds for win parameter
    mu_loss: [0.005, 0.15]   # Bounds for loss parameter
    p0: [0.52, 0.65]         # Bounds for p0 (optional)
    delta0: [0.00, 0.04]     # Bounds for delta0 (optional)
  max_change_per_run: 0.20    # Max % change per run

# PR-Q.1: Payoff parameters (auto-tuned by stats feedback loop)
payoff_mu_win:
  U: 0.040    # Ultra-short mode
  S: 0.050    # Short mode
  M: 0.080    # Medium mode
  L: 0.120    # Long mode

payoff_mu_loss:
  U: 0.020
  S: 0.030
  M: 0.040
  L: 0.060
```

## Hard Rules

1. **Offline Only**: Script never runs inside main bot loop
2. **Atomic Updates**: Uses temp file + rename for safe writes
3. **Minimum Data**: No updates if < `min_days_required` trades
4. **Bounds Checking**: All values clamped to configurable limits
5. **Deterministic**: Same input always produces same output

## Scheduling

Run via cron or systemd timer:

```bash
# /etc/cron.daily/update-strategy-params
0 2 * * * root cd /opt/strategy && \
    python strategy/optimization/update_params.py \
        --metrics data/daily_metrics.jsonl \
        --config strategy/config/params_base.yaml \
        --output strategy/config/params_base.yaml \
        --summary-json | logger -t update_params
```

## Testing

Run smoke test:

```bash
bash scripts/update_params_smoke.sh
```

Expected output:

```
[overlay_lint] running update params smoke...
[update_params_smoke] OK
```

## GREP Points

```bash
grep -n "PR-Q.1" strategy/docs/overlay/PR-Q.1.md
grep -n "update_params" strategy/optimization/update_params.py
grep -n "ewma_alpha" strategy/config/params_base.yaml
grep -n "\[update_params_smoke\] OK" scripts/update_params_smoke.sh
```

## Related PRs

- **PR-N.3**: Calibrated Inference Adapter (probability calibration)
- **PR-E.5**: Order Manager (position lifecycle)
- **PR-M.2**: Data-Track Orchestrator (metrics collection)

## Formula Integration

The updated parameters feed into the +EV calculation:

```
E[win] = payoff_mu_win[mode]     # Expected win %
E[loss] = payoff_mu_loss[mode]    # Expected loss %

EV = p_model * E[win] - (1 - p_model) * E[loss] - costs
```

As market conditions change (e.g., spread widens, fills worsen), the realized win/loss % drifts from initial estimates. This feedback loop keeps the EV formula calibrated.
