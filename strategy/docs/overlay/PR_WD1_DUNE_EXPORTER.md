# PR-WD.1 — Dune SQL Wallet Leaderboard Exporter

**Status:** In Progress  
**Owner:** Strategy Team  
**Created:** 2024-02-08

## Overview

This PR implements a pipeline for periodic export of top wallets from Dune Analytics (`dex_solana.trades` table) to the canonical `wallet_profile` format (Parquet/DuckDB). The exported data is used to initialize and refresh the wallet profiles used throughout the trading strategy.

## Goals

1. Export top wallets from Dune by metrics: `ROI_30d`, `winrate_30d`, `trades_count`, `median_hold_sec`, `memecoin_swap_ratio`
2. Normalize output to `wallet_profile` schema for downstream stages
3. Support both local fixture testing and real Dune API queries
4. Enable idempotent, deterministic exports for reproducible backtests

## Architecture

```
Dune Analytics (API)
        ↓
integration/dune_source.py (DuneWalletSource)
        ↓
strategy/profiling.py (normalize_dune_row)
        ↓
WalletProfile (canonical schema)
        ↓
Parquet/DuckDB → data/wallets/dune_export_{date}.parquet
```

## Source Schema (Dune Query Output)

Expected columns from Dune query (`dex_solana.trades` aggregation):

| Dune Column | Type | Description |
|------------|------|-------------|
| `address` | string | Wallet address |
| `roi_30d` | float | ROI percentage over 30 days |
| `winrate_30d` | float | Win rate over 30 days (0.0-1.0) |
| `trades_30d` | int | Number of trades over 30 days |
| `median_hold_sec` | int | Median holding period in seconds |
| `avg_size_usd` | float | Average trade size in USD |
| `preferred_dex` | string | Most used DEX (Raydium/Orca/Jupiter) |
| `memecoin_swaps` | int | Number of memecoin swaps |
| `total_swaps` | int | Total number of swaps |

## Target Schema (wallet_profile.v1)

```python
@dataclass(frozen=True)
class WalletProfile:
    wallet: str                              # Wallet address
    tier: Optional[str] = None               # Tier classification (tier0/tier1/tier2)
    roi_30d_pct: Optional[float] = None      # ROI percentage
    winrate_30d: Optional[float] = None      # Win rate (0.0-1.0)
    trades_30d: Optional[int] = None         # Trade count
    median_hold_sec: Optional[float] = None  # Median hold time (seconds)
    avg_trade_size_sol: Optional[float] = None # Average size in SOL
```

## Key Components

### 1. Pure Normalization (`strategy/profiling.py`)

Function `normalize_dune_row(row: dict) -> WalletProfile`:

```python
def normalize_dune_row(row: Dict[str, Any]) -> WalletProfile:
    """
    Convert Dune query output to canonical WalletProfile.
    
    - Maps Dune columns to WalletProfile fields
    - Calculates memecoin_ratio = memecoin_swaps / total_swaps
    - Converts avg_size_usd → avg_trade_size_sol (1 SOL ≈ $100)
    - Validates ranges: winrate ∈ [0, 1], trades ≥ 0
    """
```

### 2. Dune Source Adapter (`integration/dune_source.py`)

Class `DuneWalletSource`:

| Method | Description |
|--------|-------------|
| `load_from_file(path: str)` | Load from CSV/JSON fixture + normalize |
| `export_to_parquet(profiles, out_path, dry_run)` | Write to Parquet |
| `run_dune_export(...)` | Full pipeline with CLI args |

CLI Interface:
```bash
python3 -m integration.dune_source \
  --input-file fixtures/discovery/dune_export_sample.csv \
  --out-path wallets_dune.parquet \
  --dry-run \
  --summary-json
```

### 3. Daily Exporter (`tools/dune_exporter.py`)

Cron orchestration script:

- Reads config from `strategy/config/params_base.yaml`
- Exports to `data/wallets/dune_export_{YYYYMMDD}.parquet`
- Supports `--dry-run` for testing

```bash
# Daily cron entry (example)
0 2 * * * cd /path/to/strategy && python3 tools/dune_exporter.py --summary-json >> /var/log/dune_export.log 2>&1
```

### 4. Fixtures (`integration/fixtures/discovery/dune_export_sample.csv`)

Test fixture with 5 deterministic wallet records:

```csv
address,roi_30d,winrate_30d,trades_30d,median_hold_sec,avg_size_usd,preferred_dex,memecoin_swaps,total_swaps
7nYAh1wXYZ4sL5YmR8XZ1yZW2Xg6iZw4z3Xp3KZwPNp1,45.5,0.78,120,187,2450,Raydium,112,142
8pZBHm5c2k9m0n3p4r5s8t0v9w2x4y6z1a3b5c7d9e1f3h5j7,15.2,0.65,80,245,1200,Orca,45,80
...
```

## Configuration

In `strategy/config/params_base.yaml`:

```yaml
dune_export:
  enabled: true                      # Toggle Dune export on/off
  min_trades: 50                    # Minimum trades_30d threshold
  min_roi_30d: 0.1                  # Minimum ROI threshold
  out_prefix: "dune_export"         # Output file prefix
```

Environment variables:
- `DUNE_API_KEY` — Dune API key (if using real API)
- `DUNE_EXPORT_ENABLED` — Override `enabled` flag
- `DUNE_MIN_TRADES` — Override `min_trades`
- `DUNE_MIN_ROI` — Override `min_roi_30d`
- `DUNE_OUT_PREFIX` — Override `out_prefix`

## Hard Rules

| Rule | Description |
|------|-------------|
| Schema Compliance | Output must match `wallet_profile.v1` schema |
| No API Calls in Smoke | Smoke test uses ONLY local fixture |
| Stdout Contract | `--summary-json` outputs exactly 1 JSON line |
| Idempotency | Same input → bit-identical output |
| Dry-Run Safety | `--dry-run` prevents filesystem writes |

## Smoke Test

```bash
bash scripts/dune_smoke.sh
```

Expected output:
```
[overlay_lint] running dune smoke...
[dune_smoke] validated 5 wallets against wallet_profile.v1 schema
[dune_smoke] OK
```

## Integration Points

Modified files:
- `scripts/overlay_lint.sh` — Added `[dune_smoke]` to validation pipeline
- `integration/wallet_discovery.py` — Added `--skip-dune` flag to disable Dune stage

## Future Enhancements

1. **Real Dune API Integration**: Implement `DuneWalletSource.fetch_from_api()` for live queries
2. **Incremental Updates**: Export only wallets that changed since last export
3. **Multi-Query Aggregation**: Combine multiple Dune queries for richer profiles
4. **Caching Layer**: Cache Dune API responses to reduce quota usage

## GREP Points

```bash
grep -n "normalize_dune_row" strategy/profiling.py       # Line ~60
grep -n "class DuneWalletSource" integration/dune_source.py  # Line ~30
grep -n "wallet_profile.v1" integration/dune_source.py  # Line ~25
grep -n "exported_count" integration/dune_source.py      # Line ~120
grep -n "PR-WD.1" strategy/docs/overlay/PR_WD1_DUNE_EXPORTER.md  # Line 1
grep -n "\[dune_smoke\] OK" scripts/dune_smoke.sh        # Line ~30
grep -n "--skip-dune" integration/wallet_discovery.py   # (to be added)
```
