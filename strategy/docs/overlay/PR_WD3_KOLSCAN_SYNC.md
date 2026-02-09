# PR-WD.3: Kolscan API Realtime Sync

## Overview

Implements an optional adapter for syncing top trader data from Kolscan (public API or safe scraping with respect to robots.txt). The adapter enriches existing `wallet_profile` records with Kolscan-specific metadata.

## Features

### Kolscan Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `kolscan_rank` | integer | Trading rank on Kolscan platform (1 = top trader) |
| `kolscan_flags` | array | Tags: `verified`, `whale`, `memecoin_specialist` |
| `last_active_ts` | integer | Unix timestamp of last trading activity |
| `preferred_dex` | string | Always set to `"Kolscan"` when enriched |

### Source Schema (solana.ez_dex_swaps alternative)

Kolscan provides trader rankings based on DEX swap activity. Fields mapped:

| Kolscan Column | wallet_profile Field |
|----------------|---------------------|
| `wallet_address` | `wallet_addr` |
| `rank` | `kolscan_rank` |
| `tags` | `kolscan_flags` |
| `last_trade_unix` | `last_active_ts` |
| `total_volume` | (derived: avg_size_usd) |
| `win_rate` | (derived: winrate_30d) |

## Modes of Operation

### Fixture Mode (Default)

```bash
python3 -m ingestion.sources.kolscan \
  --input-file integration/fixtures/discovery/kolscan_sample.json \
  --dry-run \
  --summary-json
```

Uses local JSON fixture for testing. No network calls.

### Real API Mode (Opt-in)

```bash
python3 -m ingestion.sources.kolscan \
  --allow-kolscan \
  --wallets 4abc...,5def... \
  --dry-run \
  --summary-json
```

**Requires explicit `--allow-kolscan` flag.** Makes HTTP requests to Kolscan public pages.

## Hard Rules

1. **No Production Scraping by Default**: Real API calls only with `--allow-kolscan` flag
2. **Graceful Degradation**: Log errors to stderr, continue without failure
3. **Rate Limiting**: 1.5s delay between requests, respect `Retry-After` headers
4. **Schema Safety**: New fields are optional/nullable
5. **Smoke-Only Validation**: `overlay_lint.sh` never calls real Kolscan API

## Integration

### CLI Flags

```bash
python3 -m integration.wallet_discovery \
  --skip-dune \
  --allow-kolscan \    # Enable real Kolscan API (optional)
  --output wallets.parquet
```

### Python API

```python
from ingestion.sources.kolscan import KolscanEnricher

enricher = KolscanEnricher()
# Fixture mode only
fixture_data = enricher.load_from_file()

# With real API
enriched = enricher.enrich_wallets(
    wallets=["4abc...", "5def..."],
    allow_kolscan=True  # Requires --allow-kolscan flag in CLI
)
```

## Rate Limits & Free Tier

- **Default**: 1 request per 1.5 seconds
- **Retry-After**: Respects `Retry-After` headers (429 responses)
- **Timeout**: 10 seconds per request
- **No API key required** for public pages

## Graceful Degradation

When Kolscan is unavailable:

```python
# Error handling
try:
    data = fetch_realtime(wallets)
except Exception as e:
    logger.warning(f"Kolscan unavailable: {e}")
    data = []  # Return empty, continue processing
```

## Fixture Format

```json
[
    {
        "wallet_addr": "4abcDEFG123456789ABCDEFGHIJKLMNopqrstuvwx",
        "kolscan_rank": 17,
        "kolscan_flags": ["verified", "memecoin_specialist"],
        "last_active_ts": 1738945200
    }
]
```

## Smoke Test

```bash
bash scripts/kolscan_smoke.sh
```

Expected output:
```
[kolscan_smoke] enriched 3 wallets with kolscan metadata
[kolscan_smoke] OK
```

## Grep Points

```
grep -n "enrich_with_kolscan" strategy/profiling.py
grep -n "class KolscanEnricher" ingestion/sources/kolscan.py
grep -n "kolscan_rank" strategy/schemas/wallet_profile_schema.json
grep -n "enriched_count" ingestion/sources/kolscan.py
grep -n "PR-WD.3" strategy/docs/overlay/PR_WD3_KOLSCAN_SYNC.md
grep -n "\[kolscan_smoke\] OK" scripts/kolscan_smoke.sh
grep -n "--allow-kolscan" integration/wallet_discovery.py
```

## References

- Kolscan Website: https://kolscan.io
- API Documentation: N/A (uses public HTML pages)
