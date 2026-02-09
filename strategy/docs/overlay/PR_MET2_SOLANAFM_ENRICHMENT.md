# PR-MET.2: SolanaFM Enrichment Adapter

| Field | Value |
|-------|-------|
| **PR** | MET.2 |
| **Status** | Implemented |
| **Author(s)** | System |
| **Reviewer(s)** | TBD |
| **Created** | 2024-01-15 |
| **Updated** | 2024-01-15 |

## Overview

Optional adapter for enriching token data via public SolanaFM API. Provides verified status, creator address, holder distribution, and authority information for risk assessment.

## Features

- **Token Verification**: Fetch verified status from SolanaFM
- **Creator Attribution**: Identify token creator address
- **Holder Distribution**: Calculate top-holder concentration percentage
- **Authority Detection**: Detect mint and freeze authority presence
- **Rate Limiting**: Enforce 1 request/second (API limit)
- **Caching**: TTL-based caching (1 hour success, 5 min errors)
- **Graceful Degradation**: Fallback enrichment on API failure

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Token         │────▶│  SolanaFM        │────▶│  Enrichment     │
│  Discovery     │     │  Enricher        │     │  Cache          │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Rate Limiter    │
                       │  (1 req/sec)     │
                       └──────────────────┘
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/v1/tokens/{mint}/metadata` | Token metadata |
| `/v1/tokens/{mint}/holders` | Token holder list |

## Output Schema

```python
class SolanaFMEnrichment(BaseModel):
    mint: str                          # Token mint address
    is_verified: bool                  # Verified on SolanaFM
    creator_address: Optional[str]     # Token creator
    top_holder_pct: float              # Top 10 holders %
    holder_count: int                  # Total holders
    has_mint_authority: bool           # Mint authority exists
    has_freeze_authority: bool         # Freeze authority exists
    enrichment_ts: int                 # Unix timestamp
    source: str                       # api, fallback, fixture
```

## Honeypot Heuristics

| Indicator | Threshold | Risk Level |
|-----------|-----------|------------|
| Top holder % | > 90% | High |
| Has mint authority | True | Medium |
| Has freeze authority | True | Medium |
| Low holder count | < 100 | Medium |

## Rate Limits

- **API Limit**: 1 request/second
- **Success TTL**: 3600 seconds (1 hour)
- **Error TTL**: 300 seconds (5 minutes)
- **Timeout**: 10 seconds per request

## Configuration

```yaml
# Optional - uses public API by default
solanafm:
  api_key: "${SOLANAFM_API_KEY}"  # Optional premium API key
  timeout: 10.0                    # Request timeout
  enabled: true                    # Enable/disable adapter
```

## Integration Points

- **Token Discovery**: Optional enrichment via `--allow-solanafm`
- **Risk Engine**: Uses enrichment for honeypot detection
- **Token Snapshot**: Optional `solanafm_enrichment` field

## Testing

```bash
# Run smoke tests
./scripts/solanafm_smoke.sh

# Expected output
=== SolanaFM Enrichment Adapter Smoke Test ===
[1/4] Testing schema validation...
  ✓ Valid enrichment created successfully
  ✓ Schema validation passed
[2/4] Testing fixture loading...
  ✓ Fixture loading passed
[3/4] Testing graceful degradation...
  ✓ Graceful degradation fallback created successfully
[4/4] Testing honeypot heuristics...
  ✓ Honeypot heuristics working correctly
=== All smoke tests passed! ===
```

## Files

| File | Description |
|------|-------------|
| `ingestion/sources/solanafm.py` | Main adapter implementation |
| `strategy/schemas/solanafm_enrichment_schema.py` | Pydantic schema |
| `strategy/schemas/solanafm_enrichment_schema.json` | JSON Schema |
| `integration/fixtures/enrichment/solanafm_sample.json` | Test fixtures |
| `scripts/solanafm_smoke.sh` | Smoke test |

## Dependencies

- `aiohttp`: Async HTTP client
- `pydantic`: Schema validation

## CLI Usage

```bash
# Enrich single token
python -m ingestion.sources.solanafm EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v

# Enrich multiple tokens
python -m ingestion.sources.solanafm < fixture

# Output to file
python -m ingestion.sources.solanafm <mints> -o output.json
```

## Future Enhancements

- [ ] Redis-based caching for distributed deployments
- [ ] Batch API support for multiple tokens
- [ ] Historical holder tracking
- [ ] Creator reputation scoring
