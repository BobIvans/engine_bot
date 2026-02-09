# PR-JU.2: Raydium Pool Decoder (AMM Impact Model)

**Status:** Implemented
**Date:** 2025-02-09
**Author:** Strategy Team

## Overview

Raydium Pool Decoder adapter that fetches pool state via Solana RPC, decodes on-chain pool accounts, and calculates expected slippage using the XYK constant product formula `x*y=k`.

## Key Components

### 1. Schema (`strategy/schemas/raydium_pool_schema.json`)

Canonical schema for Raydium AMM v4 pool state:

| Field | Type | Description |
|-------|------|-------------|
| `pool_address` | string | Solana pubkey of the Raydium pool |
| `mint_x` | string | Mint address of token X (base token) |
| `mint_y` | string | Mint address of token Y (quote token, usually SOL) |
| `reserve_x` | string | Reserve amount of token X in raw units |
| `reserve_y` | string | Reserve amount of token Y in raw units |
| `lp_supply` | string | Total LP token supply |
| `fee_tier_bps` | integer | Fee tier in basis points (e.g., 25 = 0.25%) |
| `decimals_x` | integer | Decimals for token X |
| `decimals_y` | integer | Decimals for token Y |

### 2. AMM Math (`strategy/amm_math.py`)

Pure functions for slippage calculation:

```python
def estimate_slippage_bps(
    pool_address: str,
    amount_in: int,
    token_mint: str,
    reserve_in: float,
    reserve_out: float,
    fee_bps: int = 25,
) -> int:
    """
    Estimate expected slippage in basis points for a given purchase size.
    
    Uses XYK constant product formula: x * y = k
    
    Formula: Δy = y - (x*y) / (x + Δx)
    
    Returns:
        Estimated slippage in basis points (int, rounded)
    """
```

### 3. Adapter (`ingestion/sources/raydium_pool.py`)

Key functions:

- `load_fixture()` - Load pool data from JSON fixture
- `fetch_pool_via_rpc()` - Fetch and decode pool via Solana RPC
- `get_pool_for_swap()` - Get pool for specific token pair and calculate slippage
- `estimate_slippage_for_trade()` - Convenience function for slippage estimation

## Slippage Calculation

The slippage is calculated using the XYK (constant product) formula:

```
x * y = k

For a swap of Δx input tokens:
Δy = y - (x*y) / (x + Δx * (1 - fee))
```

**Slippage ratio:**
```
slippage = (ideal_output - actual_output) / ideal_output
```

Where:
- `ideal_output` = amount_in * (reserve_out / reserve_in)
- `actual_output` = calculated using XYK with fees

## Usage

### Fixture Mode (Default)
```python
from ingestion.sources.raydium_pool import get_pool_for_swap, load_fixture

# Get slippage for WIF -> SOL swap
result = await get_pool_for_swap(
    input_mint="85VBFQZC9TZkfaptBWqv14ALD9fJNuk9nz2DPvCGQq4x",
    output_mint="So11111111111111111111111111111111111111112",
    amount_in=10000000,  # 10M WIF
    use_fixture=True,
)

print(result["estimated_slippage_bps"])  # e.g., 42
```

### RPC Mode
```python
from ingestion.sources.raydium_pool import fetch_pool_via_rpc

pool = await fetch_pool_via_rpc(
    pool_address="EpX5PrYUWY7WDyjkJ5o3e3Vf9Uo5J4o9H4VrnLWDmTFF",
    rpc_url="https://api.mainnet-beta.solana.com",
)
```

### CLI
```bash
# Show all fixture pools
python -m ingestion.sources.raydium_pool

# Simulate swap
python -m ingestion.sources.raydium_pool --swap \
    85VBFQZC9TZkfaptBWqv14ALD9fJNuk9nz2DPvCGQq4x \
    So11111111111111111111111111111111111111112 \
    10000000
```

## Output Integration

### Token Snapshot Enrichment

Pool data enriches `token_snapshot.raydium_pool`:

```json
{
    "token_address": "85VBFQZC9TZkfaptBWqv14ALD9fJNuk9nz2DPvCGQq4x",
    "raydium_pool": {
        "pool_address": "EpX5PrYUWY7WDyjkJ5o3e3Vf9Uo5J4o9H4VrnLWDmTFF",
        "mint_x": "85VBFQZC9TZkfaptBWqv14ALD9fJNuk9nz2DPvCGQq4x",
        "mint_y": "So11111111111111111111111111111111111111112",
        "reserve_x": "1000000000000",
        "reserve_y": "50000000000",
        "fee_tier_bps": 25
    },
    "estimated_slippage_bps": 42
}
```

## Example Fixtures

| Pool | Token Pair | Reserves | LP Supply |
|------|------------|----------|-----------|
| `EpX5Pr...` | WIF/SOL | 1T WIF, 50 SOL | 1T LP |
| `8G9x2Y...` | BONK/SOL | 50B BONK, 2.5 SOL | 50B LP |

## Testing

```bash
# Run smoke test
chmod +x scripts/raydium_pool_smoke.sh
bash scripts/raydium_pool_smoke.sh

# Expected output:
# ========================================
# Raydium Pool Decoder Smoke Test
# PR-JU.2
# ========================================
# [1/4] Testing module import...
#   ✓ Imports successful
# [2/4] Loading and validating fixture...
#   ✓ Loaded 2 pools from fixture
# [3/4] Testing slippage calculations...
#   ✓ 1% trade slippage: ~XX bps
# [4/4] End-to-end fixture test...
#   ✓ WIF/SOL 10M WIF buy slippage: XX bps
# ========================================
# ✓ All smoke tests passed!
# ========================================
```

## Dependencies

- `httpx` - HTTP client for RPC calls
- `base58` - Solana address encoding
- `ingestion.dex.raydium.decoder` - Low-level pool decoding

## Limitations

1. **Fixture Mode**: Limited to predefined pools in fixture file
2. **RPC Mode**: Requires rate-limited RPC endpoint
3. **Pool Discovery**: Requires external index for finding pools by token pair
4. **CPMM Only**: Does not support Raydium CLMM (concentrated liquidity) pools

## Future Enhancements

- Add CLMM pool support
- Implement pool discovery via Raydium program
- Add real-time pool monitoring
- Support for multi-hop routes
