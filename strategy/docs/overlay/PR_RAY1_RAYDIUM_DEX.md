# PR-RAY.1: Raydium DEX Source Integration

> **Status:** Implemented  
> **Owner:** Ingestion Team  
> **Version:** 1.0

## Overview

This PR implements an optional trade source for Raydium CPMM (Constant Product Market Maker) pools. The adapter monitors on-chain swap events via Solana RPC, decodes logs, filters by minimum liquidity, and outputs canonical `trade_event` records.

## Architecture

```
┌─────────────────────┐
│  RaydiumDexSource   │
│  ┌─────────────────┐│
│  │ load_from_file() ││  ← Fixture mode (deterministic)
│  └─────────────────┘│
│  ┌─────────────────┐│
│  │ fetch_realtime()││  ← RPC mode (optional)
│  └─────────────────┘│
│  ┌─────────────────┐│
│  │  decode_raydium_ ││  ← Pure log decoding
│  │    cpmm_log()   ││
│  └─────────────────┘│
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Liquidity Filter   │  ← pool_reserve_sol * sol_price_usd >= $2000
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   TradeEvent        │  ← Canonical format
│   (trade_v1 schema) │
└─────────────────────┘
```

## Log Format

### Raydium CPMM Swap Log Pattern

Raydium CPMM program emits logs with the following pattern:

```
Program <PROGRAM_ID> invoke [1]
Program log: swap input_amount: <LAMPORTS> output_amount: <TOKENS> input_mint: <MINT1> output_mint: <MINT2>
Program <PROGRAM_ID> success
```

### Example Log

```
Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]
Program log: swap input_amount: 1000000000 output_amount: 42857142857 input_mint: So11111111111111111111111111111111111111112 output_mint: EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm
Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success
```

### Log Decoding Rules

| Field | Regex Pattern | Description |
|-------|---------------|-------------|
| `input_amount` | `input_amount:\s*(\d+)` | Amount in lamports (SOL) or base units (tokens) |
| `output_amount` | `output_amount:\s*(\d+)` | Amount in lamports (SOL) or base units (tokens) |
| `input_mint` | `input_mint:\s*([A-Za-z0-9]+)` | Mint address of input token |
| `output_mint` | `output_mint:\s*([A-Za-z0-9]+)` | Mint address of output token |

## Liquidity Filter

### Formula

```
pool_reserve_sol * sol_price_usd >= min_liquidity_usd
```

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `min_liquidity_usd` | $2000 | Minimum liquidity threshold |
| `pool_reserve_sol` | From pool state or fixture | SOL reserves in the pool |
| `sol_price_usd` | From fixture or RPC | SOL price in USD |

### Fallback Calculation

For the first swap from a new pool (when pool data isn't available):

```
estimated_liquidity = size_usd * 2
```

## Trade Event Schema

### Output Format (trade_v1)

```json
{
  "ts": "2024-01-01T12:00:00.000Z",
  "wallet": "RAYDIUM_CPMM_POOL",
  "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
  "side": "BUY",
  "size_usd": 100.0,
  "price": 0.0232,
  "platform": "raydium_cpmm",
  "tx_hash": "swap_283947561_So11111111_EKpQGSJt",
  "slot": 283947561,
  "pool_id": "pool_283947561",
  "source": "raydium_dex"
}
```

### Field Mapping

| Source Field | Target Field | Notes |
|--------------|--------------|-------|
| `block_time * 1000` | `ts` | Unix ms timestamp |
| Input mint = SOL | `side="BUY"` | SOL → Token |
| Input mint = Token | `side="SELL"` | Token → SOL |
| `input_amount / 1e9 * sol_price` | `size_usd` | USD value of input |
| `size_usd / token_amount` | `price` | USD price per token |
| `"raydium_cpmm"` | `platform` | Platform identifier |

## CLI Usage

### Fixture Mode (Dry Run)

```bash
python3 -m ingestion.sources.raydium_dex \
  --input-file fixtures/execution/raydium_swaps_sample.json \
  --min-liquidity-usd 2000 \
  --dry-run \
  --summary-json
```

### Real-time Mode (Requires RPC)

```bash
python3 -m ingestion.sources.raydium_dex \
  --rpc-url https://api.mainnet-beta.solana.com \
  --pool-address <POOL_ADDRESS> \
  --min-liquidity-usd 2000 \
  --lookback-slots 100
```

### Output

```json
{"trades_ingested": 3, "trades_filtered_liquidity": 2, "schema_version": "trade_v1"}
```

## Fixture Format

### Sample Fixture

```json
[
  {
    "slot": 283947561,
    "block_time": 1738945200,
    "logs": [
      "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
      "Program log: swap input_amount: 1000000000 output_amount: 42857142857 input_mint: So11111111111111111111111111111111111111112 output_mint: EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
      "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success"
    ],
    "pool_reserve_sol": 1500.0,
    "sol_price_usd": 100.0
  }
]
```

### Fixture Fields

| Field | Type | Description |
|-------|------|-------------|
| `slot` | integer | Solana slot number |
| `block_time` | integer | Unix timestamp in seconds |
| `logs` | array | Array of log strings from transaction |
| `pool_reserve_sol` | float | SOL reserves in the pool |
| `sol_price_usd` | float | SOL price in USD |

## Integration Points

### Files Modified

| File | Changes |
|------|---------|
| `integration/trade_schema.json` | Added `raydium_cpmm` to platform enum |
| `integration/trade_ingestion.py` | Added `--allow-raydium-dex` flag |
| `scripts/overlay_lint.sh` | Added `raydium_dex_smoke.sh` |

### Files Created

| File | Purpose |
|------|---------|
| `ingestion/sources/raydium_dex.py` | Raydium DEX source adapter |
| `integration/fixtures/execution/raydium_swaps_sample.json` | Test fixture with 5 swaps |
| `scripts/raydium_dex_smoke.sh` | Smoke test script |
| `strategy/docs/overlay/PR_RAY1_RAYDIUM_DEX.md` | This documentation |

## Safety & Error Handling

### Log Decoding Safety

- Only processes logs containing `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
- Ignores unrecognized logs without raising errors
- Returns `None` for invalid/malformed logs

### RPC Error Handling

- Graceful degradation: Returns partial results on RPC errors
- Logs warnings to stderr on timeout or connection errors
- Continues processing without failing the pipeline

### Liquidity Filter Edge Cases

| Scenario | Behavior |
|----------|----------|
| Pool data unavailable | Uses fallback: `size_usd * 2` |
| Zero liquidity | Swap is filtered out |
| Missing price data | Uses default $100/SOL |

## Backward Compatibility

- **Disabled by default**: No impact when `--allow-raydium-dex` flag is absent
- **Schema extension**: `raydium_cpmm` added to allowed platforms enum
- **Dry-run mode**: Fixture processing without RPC calls

## GREP Points

```bash
# Find log decoding function
grep -n "decode_raydium_cpmm_log" strategy/execution.py

# Find source class
grep -n "class RaydiumDexSource" ingestion/sources/raydium_dex.py

# Find platform enum extension
grep -n "raydium_cpmm" integration/trade_schema.json

# Find liquidity threshold
grep -n "min_liquidity_usd" ingestion/sources/raydium_dex.py

# Find documentation
grep -n "PR-RAY.1" strategy/docs/overlay/PR_RAY1_RAYDIUM_DEX.md

# Find smoke test marker
grep -n "\[raydium_dex_smoke\] OK" scripts/raydium_dex_smoke.sh

# Find integration flag
grep -n "--allow-raydium-dex" integration/trade_ingestion.py
```

## Testing

### Smoke Test

```bash
bash scripts/raydium_dex_smoke.sh
```

### Expected Output

```
[raydium_dex] decoded 5 swaps from fixture, filtered 2 (liquidity < $2000)
[raydium_dex] ingested 3 trades: 2 buys, 1 sell (platform=raydium_cpmm)
[raydium_dex_smoke] validated trades against trade_event.v1 schema
[raydium_dex_smoke] OK
```

### Fixture Test Cases

| Swap | Pool Reserves | Liquidity USD | Expected |
|------|--------------|----------------|----------|
| 1 | 1500 SOL × $100 | $150,000 | ✓ Pass |
| 2 | 2500 SOL × $100 | $250,000 | ✓ Pass |
| 3 | 5000 SOL × $100 | $500,000 | ✓ Pass |
| 4 | 15 SOL × $100 | $1,500 | ✗ Filter |
| 5 | 5 SOL × $100 | $500 | ✗ Filter |

## Related Documentation

- [Trade Schema](../integration/trade_schema.json)
- [Ingestion Sources](../ingestion/sources/base.py)
- [RPC Integration](../ingestion/rpc/client.py)
- [Raydium CPMM Program](https://github.com/raydium-io/raydium-cpmm)
