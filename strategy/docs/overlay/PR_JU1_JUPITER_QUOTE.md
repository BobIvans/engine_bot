# PR-JU.1 — Jupiter Quote API v6 Integration

## Overview

This overlay implements an optional adapter for fetching route quotes from the public Jupiter Aggregator API v6. The adapter extracts optimal swap routes for token pairs and provides standardized output in the `jupiter_route.v1` format.

## API Specification

### Endpoint

**Public Quote API** (no authentication required):
```
https://quote-api.jup.ag/v6/quote
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `inputMint` | string | Yes | Source token mint address (base58/base64 encoded) |
| `outputMint` | string | Yes | Destination token mint address |
| `amount` | integer | Yes | Amount in base units (lamports for SOL) |
| `slippageBps` | integer | No | Slippage tolerance in basis points (default: 50) |
| `swapMode` | string | No | `ExactIn` (default) or `ExactOut` |

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `inputMint` | string | Input token mint |
| `outputMint` | string | Output token mint |
| `inAmount` | string | Input amount (base units) |
| `outAmount` | string | Output amount (base units) |
| `priceImpactPct` | string | Price impact as decimal percentage |
| `routePlan` | array | DEX hop sequence |
| `contextSlot` | integer | Solana slot when quote computed |
| `timeTaken` | integer | Quote computation time (ms) |

## Free-Tier Limitations

### Rate Limits

| Tier | Requests/Second | Notes |
|------|----------------|-------|
| Public (free) | ≤3 | Implemented via `time.sleep(0.35)` delay |
| Authenticated | Higher | Not used in this implementation |

### Constraints

- Maximum 10-second cache TTL per unique quote
- Quote freshness not guaranteed for high-frequency trading
- No batch quote support in free tier

## Error Handling

### HTTP Status Codes

| Code | Meaning | Handling |
|------|---------|----------|
| 200 | Success | Normalize and return route |
| 429 | Rate Limited | Log warning, return `None` |
| 400 | Bad Request | Log error, return `None` |
| 5xx | Server Error | Log error, return `None` |

### Graceful Degradation

On any error (timeout, rate limit, server error):
1. Log warning to stderr with context
2. Return `None` (not `Exception`)
3. Pipeline continues without Jupiter data

## Integration Points

### Pipeline Integration

```python
# In integration/execution/quote_fetcher.py
fetcher = JupiterQuoteFetcher()
route = fetcher.get_best_route_for_token(
    token_mint=target_token,
    sol_amount=amount_lamports,
    allow_jupiter=args.allow_jupiter  # Default: False
)
if route:
    token_snapshot.best_route = route.to_dict()
    trade_event.route_recommendation = route.to_dict()
```

### Schema Output (`jupiter_route.v1`)

```json
{
    "route_id": "a1b2c3d4e5f6",
    "in_mint": "So11111111111111111111111111111111111111112",
    "out_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "in_amount": "1000000000",
    "out_amount": "42857142857",
    "price_impact_pct": 1.25,
    "route_plan": [
        {
            "swap_info": {
                "amm_key": "5Q544fKrFoe6tsEbD7s8PrtXkhTfD3MFMu77kNhn3W7r",
                "label": "Raydium",
                "input_mint": "So11111111111111111111111111111111111111112",
                "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            }
        }
    ],
    "context_slot": 283947561,
    "time_taken_ms": 42
}
```

## Configuration

### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--allow-jupiter` | flag | `False` | Enable real API calls |
| `--input-file` | string | - | Fixture file path |
| `--dry-run` | flag | `False` | Validate without side effects |
| `--summary-json` | flag | `False` | Output single-line JSON summary |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `JUPITER_API_URL` | Override default API endpoint |

## Testing

### Smoke Test

```bash
bash scripts/jupiter_quote_smoke.sh
```

Expected output:
```
[overlay_lint] running jupiter_quote smoke...
[jupiter_quote_smoke] Running adapter on fixture...
[jupiter_quote_smoke] validated quote against jupiter_route.v1 schema
[jupiter_quote_smoke] OK
```

### Fixture Validation

```bash
python3 -m ingestion.sources.jupiter_quote \
  --input-file fixtures/execution/jupiter_quote_sample.json \
  --in-mint So11111111111111111111111111111111111111112 \
  --out-mint EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm \
  --amount 1000000000 \
  --dry-run \
  --summary-json
```

## Backward Compatibility

### Disabled by Default

The Jupiter quote stage is **completely optional**:
- Stage disabled when `--allow-jupiter` flag absent
- Missing flag does not affect main pipeline
- `best_route` and `route_recommendation` fields remain `null` when disabled

### Cache Behavior

| Scenario | Behavior |
|----------|----------|
| Stage disabled | No cache entries created |
| Stage enabled | 10-second TTL cache per `(in_mint, out_mint, amount)` |
| Cache miss | Real API call (if allowed) or `None` |

## Performance Considerations

- **Cache Key**: `(input_mint, output_mint, amount)` tuple
- **TTL**: 10 seconds
- **Rate Limit**: 0.35s delay between API calls
- **Memory**: Minimal in-memory cache (expires automatically)

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-02-09 | Initial implementation |
