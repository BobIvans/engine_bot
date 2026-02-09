# PR-MET.1: Meteora DLMM Support

**Status:** Implemented  
**Date:** 2025-02-07  
**Owner:** Strategy Team

## Overview

This overlay adds support for Meteora DLMM (Dynamic Liquidity Market Maker) pool decoding and slippage estimation. Meteora is a Solana AMM with bin-based liquidity distribution, providing better capital efficiency for concentrated liquidity strategies.

## Features

### Bin-Based Liquidity Model

Unlike constant product AMMs (like Raydium CPMM), Meteora DLMM distributes liquidity across discrete price intervals called "bins". Each bin has a fixed price step (`bin_step_bps`) and accumulates liquidity from LPs.

**Benefits:**
- Capital efficiency: ~5-10x better than CPMM for the same price range
- Precise price impact calculation
- Support for stable and volatile pairs

### Slippage Estimation

The adapter implements a simplified slippage estimation model based on:
1. **Active bin liquidity**: Sum of liquidity in ±3 bins from current price
2. **Bin density factor**: Normalization based on bin step size
3. **Non-linear correction**: For swaps exceeding 15% of effective depth

## Architecture

```
ingestion/sources/meteora_dlmm.py
├── MeteoraPool dataclass
│   ├── pool_address: str
│   ├── mint_x: str (usually SOL)
│   ├── mint_y: str (traded token)
│   ├── current_bin_id: int
│   ├── bin_step_bps: int (bin size in bps)
│   ├── active_bin_liquidity: int
│   └── fee_tier_bps: int
│
├── MeteoraPoolDecoder class
│   ├── load_from_file() - fixture mode
│   ├── fetch_from_rpc() - real-time mode (optional)
│   └── estimate_slippage() - main estimation
│
└── SlippageResult dataclass
    ├── effective_depth_usd: float
    └── slippage_bps: int
```

## Configuration

### CLI Flags

```bash
python3 -m ingestion.sources.meteora_dlmm \
    --input-file <fixture.json> \
    --token-mint <mint_address> \
    --size-usd <trade_size> \
    --token-price-usd <price> \
    --dry-run \
    --summary-json
```

### Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `bin_step_bps` | int | - | 1-10000 | Bin step in basis points (1 = 0.01%) |
| `active_bin_liquidity` | int | - | 0+ | Liquidity in active bins |
| `size_usd` | float | - | 0+ | Trade size in USD |
| `token_price_usd` | float | - | 0+ | Current token price |

## Slippage Formula

### Step 1: Calculate Bin Density Factor

```
bin_density_factor = min(5.0, 100.0 / bin_step_bps)
```

- Smaller bin steps → higher density factor → more concentrated liquidity
- Capped at 5.0 to prevent overestimation

### Step 2: Calculate Effective Depth

```
effective_depth_usd = (active_bin_liquidity / 1e6) * token_price_usd * bin_density_factor
```

### Step 3: Calculate Slippage

**For small swaps (≤15% of depth):**
```
slippage_pct = size_ratio * 100.0
slippage_bps = slippage_pct * 100
```

**For large swaps (>15% of depth):**
```
slippage_pct = size_ratio * 100.0 * (1.0 + 0.7 * (size_ratio - 0.15) / 0.85)
slippage_bps = min(10000, slippage_pct * 100)
```

### Example

Pool: `bin_step_bps=10`, `active_bin_liquidity=500M`, `token_price=1.00`

```
bin_density_factor = min(5.0, 100.0/10) = 5.0
effective_depth_usd = (500M/1e6) * 1.00 * 5.0 = 2500
```

**$3000 buy (120% of depth):**
```
size_ratio = 3000 / 2500 = 1.2
slippage_pct = 1.2 * 100 * (1 + 0.7 * (1.2 - 0.15) / 0.85) = 223.8%
slippage_bps = min(10000, 223.8 * 100) = 9999
```

**$500 buy (20% of depth):**
```
size_ratio = 500 / 2500 = 0.2
slippage_pct = 0.2 * 100 * (1 + 0.7 * (0.2 - 0.15) / 0.85) = 20.82%
slippage_bps = 2082
```

## Integration Points

### With Execution Stage

```python
from ingestion.sources.meteora_dlmm import MeteoraPoolDecoder

decoder = MeteoraPoolDecoder(dry_run=True)
pool = decoder.load_from_file("fixtures.json", token_mint)

if pool:
    result = decoder.estimate_slippage(pool, size_usd=3000, token_price_usd=1.0)
    slippage_bps = result.slippage_bps
```

### With Risk Management

- Pools with `slippage_bps > 500` (5%) may be flagged for reduced position size
- Pools with `slippage_bps > 1000` (10%) may be rejected entirely
- Consider gas costs + slippage for net execution quality

## Meteora Program ID

```
LBUZKhRxPF3XUpBCjp4YzTKgLccj5HBQVXMCmTrxASL
```

## Limitations

1. **Simplified decoding**: Account structure decoding is simplified for prototype
2. **No RPC by default**: Real-time fetching requires `--allow-meteora-dlmm` flag
3. **Bin arithmetic**: Does not account for bin crossing during large swaps
4. **Fee tier**: Protocol fee not included in slippage calculation

## Testing

```bash
# Run smoke test
bash scripts/meteora_dlmm_smoke.sh

# Expected output:
# [meteora_dlmm_smoke] Estimated slippage: 9999 bps
# [meteora_dlmm_smoke] OK
```

## Future Enhancements

1. **Full Borsh deserialization**: Support all pool versions
2. **Bin crossing calculation**: Account for multi-bin swaps
3. **Oracle integration**: Use on-chain oracles for price validation
4. **Active range tracking**: Monitor when price exits active bin range
