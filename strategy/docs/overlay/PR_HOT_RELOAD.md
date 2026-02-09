# PR-Y.5: Config Hot-Reload

## Overview
Implements a thread-safe hot-reload mechanism for specific whitelisted runtime configuration parameters without restarting the bot.

## Usage
Run the pipeline with the `--hot-reload-config` flag:
```bash
python3 -m integration.paper_pipeline --config strategy/config/params_base.yaml --hot-reload-config ...
```

## Whitelisted Parameters
Only the following parameters can be updated at runtime. Changes to other fields are ignored.

### Signal Engine (signals.*)
- `edge_threshold_base` (float, 0.0-1.0)
- `edge_threshold_riskon` (float, 0.0-1.0)
- `edge_threshold_riskoff` (float, 0.0-1.0)

### Risk Manager (risk.*)
- `position_pct` (float, 0.005-0.05) → maps to `risk.sizing.fixed_pct_of_bankroll`
- `max_open_positions` (int, 1-10)
- `max_token_exposure` (float, 0.01-0.50) → `max_exposure_per_token_pct`
- `max_daily_loss` (float, 0.01-0.20) → `max_daily_loss_pct`
- `kelly_fraction` (float, 0.1-1.0)
- `cooldown_after_losses_sec` (int) → `risk.limits.cooldown.duration_sec`

## Architecture
- **Infrastructure**: `config/hot_reload.py` runs a background thread watching the config file mtime.
- **Schema**: `config/runtime_schema.py` defines the whitelist and validation logic (using dataclasses).
- **Integration**: `integration/config_loader.py` manages the reloader and merges updates.
- **Pipeline**: `integration/paper_pipeline.py` applies overrides at the start of each input processing loop.

## Safety
- Atomic updates via `threading.RLock`.
- Validation ensures invalid values (e.g. `edge_threshold > 1.0`) are rejected and the previous valid config is preserved.
- Errors are logged to stderr.

## Testing
Run the smoke test to verify:
```bash
bash scripts/config_hot_reload_smoke.sh
```
