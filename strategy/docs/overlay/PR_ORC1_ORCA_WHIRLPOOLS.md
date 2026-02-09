# PR-ORC.1: Orca Whirlpools Support (Concentrated Liquidity)

**Status:** Implemented
**Date:** 2025-02-09
**Author:** Strategy Team

## Overview

Optional adapter for decoding Orca Whirlpool concentrated liquidity pools (Uniswap V3 style), extracting key pool parameters, and calculating simplified price impact for swaps.

## Key Components

### 1. Schema (`strategy/schemas/orca_pool_schema.json`)

Canonical schema for Orca Whirlpool state:

| Field | Type | Description |
|-------|------|-------------|
| `pool_address` | string | Solana pubkey of the Whirlpool |
| `mint_x` | string | Mint address of token X (usually SOL) |
| `mint_y` | string | Mint address of token Y (traded token) |
| `sqrt_price_x64` | string | Square root of price as Q64.64 integer |
| `tick_current` | integer | Current tick position |
| `liquidity` | string | Current liquidity (Q64.64) |
| `tick_spacing` | integer | Tick spacing (e.g., 64, 128) |
| `fee_tier_bps` | integer | Fee tier in basis points |

### 2. AMM Math (`strategy/amm_math.py`)

Pure function for concentrated liquidity slippage:

```python
def estimate_whirlpool_slippage_bps(
    liquidity: int,           # Q64.64 liquidity
    sqrt_price_x64: int,     # sqrt(price) * 2^64
    tick_spacing: int,       # tick spacing
    size_usd: float,         # purchase size in USD
    token_price_usd: float,  # token price in USD
    sol_price_usd: float = 100.0,
) -> int:
    """Simplified slippage estimation for CLM."""
```

### 3. Adapter (`ingestion/sources/orca_whirlpools.py`)

Key methods:
- `load_from_file(path, token_mint)` - Load pool from fixture
- `fetch_from_rpc(token_mint, rpc_url, allow_orca)` - RPC fetch (optional)
- `estimate_slippage_for_token(pool, size_usd, token_price)` - Calculate slippage

## Slippage Model

**Concentrated Liquidity Formula:**
- Effective liquidity depth: `liquidity * sqrt_price * tick_spacing_factor`
- `tick_spacing_factor = max(1.0, tick_spacing / 64.0)`
- Slippage approximation: `slippage_pct ≈ (size_usd / effective_liquidity) * 100`

**Non-linear correction for large trades (>10%):**
```
slippage_pct *= (1 + 0.5 * (size_ratio - 0.1) / 0.9)
```

## Usage

### Fixture Mode (Default)
```python
from ingestion.sources.orca_whirlpools import OrcaWhirlpoolDecoder

decoder = OrcaWhirlpoolDecoder()
pool = decoder.load_from_file(
    "fixtures/execution/orca_pool_sample.json",
    token_mint="DeXkVx9f7eVN6FJqzsdMps4xE6K7LxY6TiqTLT4zSZ"
)

slippage = decoder.estimate_slippage_for_token(
    pool=pool,
    size_usd=5000,
    token_price_usd=0.8,
)
```

### CLI
```bash
python3 -m ingestion.sources.orca_whirlpools \
  --input-file fixtures/execution/orca_pool_sample.json \
  --token-mint DeXkVx9f7eVN6FJqzsdMps4xE6K7LxY6TiqTLT4zSZ \
  --size-usd 5000 \
  --token-price-usd 0.8 \
  --summary-json
```

## Fixture Data

| Pool | Token | Liquidity | Tick Spacing | Fee |
|------|-------|------------|--------------|-----|
| `71xG9...` | High liquidity SOL/token | 1.5e18 | 64 | 25 bps |
| `92yH8...` | Low liquidity memecoin | 1.2e17 | 128 | 100 bps |

## Output Integration

Pool data enriches `token_snapshot.orca_pool`:

```json
{
    "token_address": "DeXkVx...",
    "orca_pool": {
        "pool_address": "71xG9...",
        "mint_x": "So111...",
        "mint_y": "DeXkVx...",
        "sqrt_price_x64": "302148...",
        "tick_current": 25200,
        "liquidity": "1500000000000000000",
        "tick_spacing": 64,
        "fee_tier_bps": 25
    },
    "estimated_slippage_bps": 670
}
```

## Testing

```bash
# Run smoke test
bash scripts/orca_whirlpools_smoke.sh

# Expected output:
# ========================================
# Orca Whirlpools Smoke Test
# PR-ORC.1
# ========================================
# [1/5] Testing module import...
#   ✓ Imports successful
# [2/5] Loading and validating fixture...
#   ✓ Loaded 2 pools from fixture
# [3/5] Testing pool lookup...
#   ✓ Found pools by token mint
# [4/5] Testing slippage calculations...
#   ✓ High liquidity pool: ~670 bps
#   ✓ Low liquidity pool: ~7500 bps
# [5/5] End-to-end decoder test...
#   ✓ JSON output format valid
# ========================================
# ✓ All smoke tests passed!
# [orca_whirlpools_smoke] OK
# ========================================
```

## Dependencies

- `httpx` - HTTP client for RPC (optional, graceful fallback)
- `base58` - Solana address encoding

## Limitations

1. **Simplified Model**: Uses `pool.liquidity` as proxy for active liquidity
2. **No Tick Iteration**: Doesn't process all positions in a range
3. **Fixture Mode**: Limited to predefined pools
4. **RPC Optional**: Real RPC calls require `--allow-orca-whirlpools` flag

## Future Enhancements

- Full tick map processing
- Multi-tick range analysis
- Real-time liquidity monitoring
- Cross-pool comparison
