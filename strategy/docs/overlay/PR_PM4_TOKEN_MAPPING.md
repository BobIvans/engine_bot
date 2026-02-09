# PR-PM.4: Polymarket → Solana Token Mapping

**Status:** Implemented  
**Date:** 2024-02-09  
**Owner:** ML Platform Team

## Overview

PR-PM.4 implements semantic mapping of Polymarket prediction markets to Solana memecoins. This enables signal boosting on relevant tokens when market probabilities move.

## Mapping Strategies

### Priority Order

Mappings are computed in priority order, with higher-priority matches receiving higher relevance scores:

| Priority | Strategy | Score | Description |
|----------|----------|-------|-------------|
| 1 | `exact_symbol` | 1.0 | Token symbol appears with `$` prefix in question |
| 2 | `thematic` | 0.8 | Market theme matches token whitelist (politics, animals, sports) |
| 3 | `fuzzy_name` | 0.6 | Normalized words from token name match question |

### Exact Symbol Matching

Extracts `$SYMBOL` patterns from market questions and matches against token symbols.

**Examples:**
- Question: "Will `$TRUMP` win the 2024 election?"
- Match: `$TRUMP` → `TRUMP` token (score: 1.0)

### Thematic Matching

Classifies markets by theme keywords, then maps to whitelisted tokens.

**Themes and Keywords:**
```
politics: trump, harris, biden, election, president, vote, democrat, republican
animals: dog, cat, wolf, bonk, hat, wif, pepe, frog, shib, inu
sports: goat, ball, champ, super bowl, olympic, messi, ronaldo
```

**Theme Token Whitelists:**
```
politics: TRUMP, HARRIS, MELANIA, BIDEN, OBAMA, CLINTON
animals: WIF, BONK, POPCAT, DOGE, PEPE, FLOKI, SHIB
sports: GOAT, CHAMP, BALL
```

### Fuzzy Name Matching

Tokenizes token names and matches individual words against the normalized question.

**Example:**
- Token name: "Dogwifhat" → tokens: ["dog", "wif", "hat"]
- Question: "Will dog memes dominate?"
- Match: "dog" → score: 0.6

## Deduplication

When a token matches via multiple strategies, only the highest-scoring match is retained.

**Example:**
- Question: "Will `$TRUMP` win?"
- Token `$TRUMP` matches via `exact_symbol` (1.0) and `thematic` (0.8)
- Result: `$TRUMP` with score 1.0

## Output Schema

```json
{
  "market_id": "trump-wins-2024",
  "token_mint": "TRUMP11111111111111111111111111111111111",
  "token_symbol": "TRUMP",
  "relevance_score": 1.0,
  "mapping_type": "exact_symbol",
  "matched_keywords": ["TRUMP"],
  "ts": 1738945200000,
  "schema_version": "pm4_v1"
}
```

## Test Fixtures

### Markets (`integration/fixtures/sentiment/polymarket_sample_mapping.json`)

| ID | Question | Expected Mappings |
|----|----------|------------------|
| `trump-wins-2024` | Will `$TRUMP` win the 2024 election? | $TRUMP (exact, 1.0), $HARRIS (thematic, 0.8), $MELANIA (thematic, 0.8) |
| `dog-meme-season` | Will dog-themed memes dominate 2025? | $WIF (thematic, 0.8), $BONK (thematic, 0.8), $POPCAT (fuzzy, 0.6) |
| `goat-athlete` | Will LeBron be considered the GOAT by 2030? | $GOAT (exact, 1.0) |
| `quantum-computing` | Will quantum computing break RSA? | None |

### Tokens (`integration/fixtures/discovery/token_snapshot_sample_mapping.csv`)

| Symbol | Name | Theme |
|--------|------|-------|
| TRUMP | Trump | politics |
| HARRIS | Harris | politics |
| MELANIA | Melania | politics |
| WIF | Dogwifhat | animals |
| BONK | Bonk | animals |
| POPCAT | Popcat | animals |
| GOAT | Goat | sports |
| MOON | Moon | generic |

## Smoke Test

```bash
bash scripts/token_mapping_smoke.sh
```

Expected output:
```
[overlay_lint] running token_mapping smoke...
[token_mapping_smoke] built 6 mappings across 3 markets (max relevance=1.0)
[token_mapping_smoke] OK
```

## CLI Usage

```bash
python3 -m ingestion.pipelines.token_mapping_pipeline \
  --input-polymarket polymarket_snapshots.parquet \
  --input-tokens token_snapshot.parquet \
  --output polymarket_token_mapping.parquet \
  --dry-run \
  --summary-json
```

## Integration

In `integration/wallet_discovery.py`:
- Flag: `--skip-token-mapping` (default: False)
- Called after event risk computation
- Output: `data/sentiment/polymarket_token_mapping.parquet`

## Related PRs

- **PR-PM.3**: Event Risk Aggregator (complementary sentiment analysis)
- **PR-ML.2**: Core feature pipeline (uses token mappings for signal boosting)

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-02-09 | Initial implementation |
