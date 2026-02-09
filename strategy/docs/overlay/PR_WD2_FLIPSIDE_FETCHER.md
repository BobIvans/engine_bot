# PR-WD.2: Flipside Solana.ez_dex_swaps Alternative Fetcher

<!--
PR references: PR-WD.2
Owner: Strategy Team
Status: Active
Deprecation Banner: N/A
-->

## Overview

This PR implements a parallel data source for wallet discovery through Flipside Crypto, specifically targeting the `solana.ez_dex_swaps` table. The adapter extracts ROI/winrate/median_hold metrics from historical swaps, normalizes them to the canonical `wallet_profile` format, and serves as a fallback/verification source to Dune.

## Motivation

The existing wallet discovery pipeline relies primarily on Dune for wallet metrics. This PR introduces Flipside as:

1. **Fallback/Verification**: Provides an alternative data source if Dune is unavailable or has data quality issues
2. **Parallel Processing**: Enables concurrent wallet discovery from multiple data sources
3. **Data Validation**: Allows cross-referencing metrics between Flipside and Dune for quality assurance

## Architecture

### Source Adapter (`ingestion/sources/flipside.py`)

The main adapter provides two modes of operation:

1. **Local Fixture Mode** (default): Loads wallet profiles from CSV/JSONL fixture files for testing
2. **Real API Mode** (optional): Queries Flipside API directly for live data

#### CLI Interface

```bash
# Run with fixture file (testing mode)
python3 -m ingestion.sources.flipside \
  --input-file fixtures/discovery/flipside_sample.csv \
  --out-path wallets_flipside.parquet \
  --dry-run \
  --summary-json

# Run with Flipside API (production mode)
python3 -m ingestion.sources.flipside \
  --api-key $FLIPSIDE_API_KEY \
  --use-api \
  --api-query "SELECT swapper, roi_30d, ... FROM solana.ez_dex_swaps" \
  --out-path wallets_flipside.parquet
```

### Flipside Schema Mapping

The adapter maps `solana.ez_dex_swaps` columns to the canonical `wallet_profile` schema:

| Flipside Column | wallet_profile Field | Description |
|----------------|----------------------|-------------|
| `swapper` | `wallet_addr` | Wallet public key |
| `roi_30d` / `pnl_percentage` | `roi_30d` | 30-day ROI as decimal (e.g., 0.38 = 38%) |
| `winrate_30d` | `winrate_30d` | 30-day win rate (0.0-1.0) |
| `trades_30d` | `trades_30d` | Number of trades in 30-day window |
| `median_hold_sec` | `median_hold_sec` | Median hold time in seconds |
| `avg_size_usd` | `avg_size_usd` | Average trade size in USD |
| `preferred_dex` / `dex` | `preferred_dex` | Most-used DEX (Raydium, Jupiter, etc.) |
| `memecoin_swaps` / `total_swaps` | `memecoin_ratio` | Calculated as memecoin_swaps / total_swaps |

### Wallet Profile Schema (Output)

The adapter outputs profiles conforming to `wallet_profile.v1`:

```json
{
  "wallet_addr": "4abcDEFG123456789ABCDEFGHIJKLMNopqrstuvwx",
  "roi_30d": 0.38,
  "winrate_30d": 0.72,
  "trades_30d": 98,
  "median_hold_sec": 215,
  "avg_size_usd": 1890.0,
  "preferred_dex": "Raydium",
  "memecoin_ratio": 0.8877551020408163
}
```

### Validation Rules

The adapter enforces the following validation rules:

1. **Required Fields**: `wallet_addr` must be present and non-empty
2. **Winrate Range**: `winrate_30d` must be between 0.0 and 1.0
3. **Trades Non-Negative**: `trades_30d` must be >= 0
4. **Hold Time Non-Negative**: `median_hold_sec` must be >= 0
5. **Memecoin Ratio**: Auto-calculated if not provided directly

## Integration

### Wallet Discovery Pipeline (`integration/wallet_discovery.py`)

The Flipside source is integrated into the wallet discovery pipeline with an optional `--skip-flipside` flag:

```python
# In build_wallet_profiles()
def build_wallet_profiles(
    dune_input: str,
    flipside_input: str | None = None,
    skip_flipside: bool = False,
    output: str = "-"
) -> WalletDiscoverySummary:
    # Load Dune profiles
    dune_profiles = load_dune_profiles(dune_input)
    
    # Load Flipside profiles (if not skipped)
    flipside_profiles = []
    if not skip_flipside and flipside_input:
        source = FlipsideWalletSource()
        flipside_profiles = source.load_from_file(flipside_input)
    
    # Merge profiles (Flipside serves as verification/fallback)
    all_profiles = merge_wallet_profiles(
        dune_profiles, 
        flipside_profiles,
        strategy="prefer_higher_roi"
    )
    
    return all_profiles
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--skip-flipside` | False | Skip Flipside source entirely |
| `--flipside-input` | None | Path to Flipside fixture/CSV file |

## Fixtures

### Sample Data (`integration/fixtures/discovery/flipside_sample.csv`)

Deterministic fixture with 5 wallets covering various scenarios:

| Wallet | ROI | Winrate | Trades | Median Hold | DEX | Memecoin Ratio |
|--------|-----|---------|--------|-------------|-----|----------------|
| 4abc... | 38% | 72% | 98 | 215s | Raydium | 89% |
| 5def... | 51% | 81% | 215 | 94s | Jupiter | 92% |
| 6cde... | 22% | 58% | 42 | 420s | Orca | 90% |
| 7abcd... | 67% | 89% | 310 | 67s | Raydium | 90% |
| 8efgh... | 45% | 75% | 156 | 180s | Meteora | 91% |

## Smoke Test

The smoke test validates:

1. **Schema Compliance**: Output matches `wallet_profile.v1` schema
2. **Metric Validation**: All 5 wallets have valid metrics in expected ranges
3. **Dry Run Mode**: No filesystem writes during testing
4. **Summary JSON**: Correct output format with `exported_count` and `schema_version`

```bash
# Run smoke test
bash scripts/flipside_smoke.sh

# Expected output
[overlay_lint] running flipside smoke...
[flipside_smoke] validated 5 wallets against wallet_profile.v1 schema
[flipside_smoke] OK
```

## Hard Rules Compliance

| Rule | Compliance |
|------|------------|
| Schema Compliance | ✅ Output strictly conforms to `wallet_profile.v1` |
| No API Calls in Smoke | ✅ Smoke test uses only local fixture |
| Stdout Contract | ✅ `--summary-json` outputs exactly one JSON line |
| Idempotency | ✅ Deterministic CSV → identical output |
| Backward Compatibility | ✅ Fully optional via `--skip-flipside` |
| Dry-Run Safety | ✅ `--dry-run` prevents filesystem writes |

## Flipside Query Example

For production API usage, the following query pattern extracts wallet metrics:

```sql
SELECT
  swapper AS wallet_addr,
  AVG(pnl_percentage) AS roi_30d,
  AVG(win_rate) AS winrate_30d,
  COUNT(*) AS trades_30d,
  AVG(median_hold_time_seconds) AS median_hold_sec,
  AVG(swap_usd_value) AS avg_size_usd,
  MODE() WITHIN GROUP (ORDER BY program_id) AS preferred_dex,
  COUNT(CASE WHEN is_memecoin THEN 1 END) AS memecoin_swaps,
  COUNT(*) AS total_swaps
FROM solana.ez_dex_swaps
WHERE block_timestamp > NOW() - INTERVAL '30 DAY'
GROUP BY swapper
```

## Dependencies

- `requests` - For Flipside API calls
- `duckdb` - For Parquet export
- Standard library: `argparse`, `csv`, `json`, `dataclasses`

## GREP Points

```bash
grep -n "normalize_flipside_row" strategy/profiling.py
grep -n "class FlipsideWalletSource" ingestion/sources/flipside.py
grep -n "wallet_profile.v1" ingestion/sources/flipside.py
grep -n "exported_count" ingestion/sources/flipside.py
grep -n "PR-WD.2" strategy/docs/overlay/PR_WD2_FLIPSIDE_FETCHER.md
grep -n "\[flipside_smoke\] OK" scripts/flipside_smoke.sh
grep -n "--skip-flipside" integration/wallet_discovery.py
```
