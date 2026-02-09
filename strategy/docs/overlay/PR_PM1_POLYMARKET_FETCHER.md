# PR-PM.1: Polymarket Gamma API Snapshot Fetcher

**Status:** Implemented  
**Date:** 2024-01-  
**Owner:** Strategy Team

---

## Overview

This PR implements an optional adapter for periodically snapshotting Polymarket market data from the public Gamma API. The adapter extracts active markets with fields including `id`, `question`, `price1`/`price2` (outcome probabilities), `volumeUSD`, and `eventExpirationDate`. The data is transformed into the canonical `polymarket_snapshot` format and saved to Parquet/DuckDB.

## API Specification

### Endpoint

```
GET https://gamma-api.polymarket.com/markets
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `active` | boolean | Filter to active markets only |

### Rate Limits

- **Free Tier:** ≤1 request/minute recommended
- **Production:** Use fixture mode for tests, cache results
- **Graceful Degradation:** On 429/5xx/timeout → log to stderr, continue without error

### Response Format (Raw)

```json
{
  "data": [
    {
      "id": "market-uuid",
      "question": "Will Bitcoin exceed $100K by EOY?",
      "price1": 0.78,
      "outcome1": "Yes",
      "price2": 0.22,
      "outcome2": "No",
      "volumeUSD": 1245000,
      "eventExpirationDate": "2024-12-31T23:59:59Z",
      "active": true
    }
  ]
}
```

## Field Mapping

| Raw Field | Canonical Field | Notes |
|-----------|-----------------|-------|
| `id` | `market_id` | Unique identifier |
| `question` | `question` | Market question text |
| `price1` | `p_yes` | Assumed YES outcome |
| `1.0 - price1` | `p_no` | Calculated |
| `volumeUSD` | `volume_usd` | USD volume |
| `eventExpirationDate` | `event_date` | ISO → Unix ms |

## Category Tagging

Markets are automatically tagged based on question keywords:

| Keyword Pattern | Tags |
|-----------------|------|
| Bitcoin / BTC | `["crypto", "bitcoin"]` |
| Ethereum / ETH | `["crypto", "ethereum"]` |
| Solana / SOL | `["crypto", "solana"]` |
| Trump | `["politics", "us_election"]` |
| Harris | `["politics", "us_election"]` |
| Election / President | `["politics"]` |
| S&P 500 | `["finance"]` |
| Inflation / GDP | `["economics"]` |
| Super Bowl / Olympics | `["sports"]` |
| Default | `["general"]` |

## Schema

See [`polymarket_snapshot_schema.json`](../../../schemas/polymarket_snapshot_schema.json) for full JSON Schema definition.

```json
{
  "type": "object",
  "properties": {
    "ts": {"type": "integer", "minimum": 0},
    "market_id": {"type": "string", "minLength": 1},
    "question": {"type": "string"},
    "p_yes": {"type": "number", "minimum": 0, "maximum": 1},
    "p_no": {"type": "number", "minimum": 0, "maximum": 1},
    "volume_usd": {"type": "number", "minimum": 0},
    "event_date": {"type": "integer", "minimum": 0},
    "category_tags": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["ts", "market_id", "question", "p_yes", "p_no", "volume_usd", "event_date", "category_tags"]
}
```

## Usage

### CLI (Fixture Mode)

```bash
# Load from fixture with fixed timestamp
python3 -m ingestion.sources.polymarket \
    --input-file fixtures/sentiment/polymarket_sample.json \
    --fixed-ts=1738945200000 \
    --summary-json

# Output to parquet
python3 -m ingestion.sources.polymarket \
    --input-file fixtures/sentiment/polymarket_sample.json \
    --output polymarket_snapshots.parquet \
    --fixed-ts=1738945200000
```

### API Mode (Optional)

```bash
# Enable real API calls (disabled by default)
python3 -m ingestion.sources.polymarket \
    --allow-api \
    --output polymarket_snapshots.parquet
```

### Python API

```python
from ingestion.sources.polymarket import PolymarketSnapshotFetcher

fetcher = PolymarketSnapshotFetcher()

# Load from fixture
snapshots = fetcher.load_from_file(
    path="fixtures/sentiment/polymarket_sample.json",
    fixed_ts=1738945200000
)

# Or fetch from API
snapshots = fetcher.fetch_realtime(
    allow_polymarket=True,
    fixed_ts=None  # Use current time
)

# Export to parquet
fetcher.export_to_parquet(snapshots, "output.parquet")
```

## Integration

### Wallet Discovery Integration

The snapshot fetcher can be integrated into wallet discovery via the `--allow-polymarket` flag:

```bash
python3 -m integration.wallet_discovery \
    --allow-polymarket \
    --config config.yaml
```

Without the flag, the Polymarket stage is skipped gracefully.

### Smoke Test

```bash
bash scripts/polymarket_smoke.sh
```

Expected output:
```
[overlay_lint] running polymarket smoke...
[polymarket_smoke] validated 5 markets against polymarket_snapshot.v1 schema
[polymarket_smoke] OK
```

## Validation Rules

1. **Probability Sum:** `abs(p_yes + p_no - 1.0) < 0.01` (tolerance for rounding)
2. **Required Fields:** `id`, `question`, `price1`, `volumeUSD`, `eventExpirationDate`
3. **Non-Negative:** `volume_usd >= 0`, `p_yes >= 0`, `p_no >= 0`
4. **Valid Range:** `p_yes <= 1.0`, `p_no <= 1.0`

## Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| API rate limited (429) | Log warning, return empty list |
| Server error (5xx) | Log warning, return empty list |
| Timeout | Log warning, return empty list |
| Missing fixture file | Log warning, return empty list |
| Validation error | Skip market, log warning |
| `--allow-api=false` | Return empty list (default) |

## Files

| File | Purpose |
|------|---------|
| `ingestion/sources/polymarket.py` | PolymarketClient + PolymarketSnapshotFetcher |
| `strategy/sentiment.py` | normalize_polymarket_market() |
| `strategy/schemas/polymarket_snapshot_schema.json` | JSON Schema |
| `integration/fixtures/sentiment/polymarket_sample.json` | Test fixture (5 markets) |
| `scripts/polymarket_smoke.sh` | Smoke test |

## GREP Points

```bash
grep -n "normalize_polymarket_market" strategy/sentiment.py
grep -n "class PolymarketSnapshotFetcher" ingestion/sources/polymarket.py
grep -n "polymarket_snapshot.v1" ingestion/sources/polymarket.py
grep -n "snapshot_count" ingestion/sources/polymarket.py
grep -n "PR-PM.1" strategy/docs/overlay/PR_PM1_POLYMARKET_FETCHER.md
grep -n "\[polymarket_smoke\] OK" scripts/polymarket_smoke.sh
grep -n "--allow-polymarket" integration/wallet_discovery.py
```
