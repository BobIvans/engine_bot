# PR-Y.3 — Flipside Historical Backfill (Dune Alternative Source)

## Overview

This PR implements an optional data source for historical trade data from Flipside Crypto, providing an alternative to Dune Analytics and reducing dependency on a single data provider.

## Architecture

### Pure Logic (`strategy/ingestion.py`)

The `normalize_flipside_trade()` function transforms raw Flipside data into the canonical `TradeEvent` format:

```python
def normalize_flipside_trade(row: Dict[str, Any]) -> Tuple[Optional[TradeEvent], Optional[str]]:
    """
    Normalize a Flipside trade row into a TradeEvent.
    
    Args:
        row: Dictionary from Flipside query result
        
    Returns:
        Tuple of (TradeEvent, reject_reason)
    """
```

### Integration Stage (`integration/flipside_ingestion.py`)

The stage is **optional** and controlled by the `--use-flipside` flag:

```bash
python -m integration.flipside_ingestion \
    --use-flipside \
    --source <file.jsonl> \
    --out <output.jsonl> \
    --rejects <rejects.jsonl>
```

Without `--use-flipside`, the stage acts as a no-op (returns empty metrics).

## Data Mapping

### Flipside Schema → TradeEvent

| Flipside Field | TradeEvent Field | Required |
|----------------|-----------------|----------|
| `block_timestamp` | `timestamp` | Yes |
| `swapper` | `wallet` | Yes |
| `token_mint` | `mint` | Yes |
| `token_amount` | `amount` | Yes |
| `usd_amount` | `value_usd` | Yes |
| `program_id` | `platform` | Yes |
| `tx_hash` | `tx_hash` | Yes |
| `price_per_token` | `price_usd` | No (calculated) |

### Platform Mapping

| Program ID | Platform |
|------------|----------|
| `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | raydium |
| `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | orca |
| `JUP6LkbZbjS1jKKwapnHNygxzwHrQ32NqwnVERy8ls` | jupiter |
| `22Y43yTVxuUvsRKqL4cc4nkrGC1TqnBsvZ62U4U2CN4` | pumpfun |
| `Df6yfrKC5kHEzq1bRzj5zL5AKcFmqz6A4LZTKbwP2Q2` | moonshot |
| `CAMMCzo5YL8w4VFF1KVztvNZ3HWTA7raSqoLAeCYgzEt` | meteora |

## Reject Reasons

| Reason | Description |
|--------|-------------|
| `FLIPSIDE_MISSING_REQUIRED_FIELD` | Required field is missing or null |
| `FLIPSIDE_SCHEMA_MISMATCH` | Schema validation failed |
| `FLIPSIDE_INVALID_PROGRAM_ID` | Cannot calculate price (division by zero) |

## Metrics

| Metric | Description |
|--------|-------------|
| `flipside_total` | Total rows processed |
| `flipside_accepted` | Successfully normalized trades |
| `flipside_rejected` | Failed validation |

## Usage

### Integration with Paper Pipeline

Add to `integration/paper_pipeline.py`:

```python
# After trade_normalizer
if args.use_flipside:
    flipside_metrics = run_flipside_stage(
        source_path=args.flipside_source,
        out_path=Path("flipside_normalized.jsonl"),
        rejects_path=Path("flipside_rejects.jsonl"),
    )
    metrics.update(flipside_metrics)
```

### CLI Integration

```bash
# With Flipside data
python -m integration.paper_pipeline \
    --use-flipside \
    --flipside-source data/flipside_trades.jsonl

# Without (default behavior unchanged)
python -m integration.paper_pipeline
```

## Testing

### Smoke Test

```bash
bash scripts/flipside_smoke.sh
```

Expected output:
```
[flipside_smoke] flipside_total=5 ✅
[flipside_smoke] flipside_accepted=3 ✅
[flipside_smoke] flipside_rejected=2 ✅
[flipside_smoke] OK
```

### Fixture Data

Located in `integration/fixtures/flipside/`:
- `wallet_trades_sample.jsonl` - 5 trades (3 valid, 2 invalid)
- `wallet_profiles_sample.csv` - 3 wallet profiles
- `expected_normalized_trades.jsonl` - Expected output

## Constraints

1. **No API calls in tests** - Smoke tests use fixtures only
2. **stdout-contract** - `--summary-json` outputs exactly 1 line JSON
3. **Optional by default** - Pipeline works without Flipside data
4. **No vendor changes** - All code in `integration/` and `strategy/`
