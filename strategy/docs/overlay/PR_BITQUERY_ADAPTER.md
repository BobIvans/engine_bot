# PR-Y.4: Bitquery GraphQL Adapter Specification

## Schema Mapping

Maps Bitquery Solana GraphQL schema to internal `TradeEvent`.

### Required Fields

| Bitquery Field | TradeEvent Field | Validation |
|----------------|------------------|------------|
| `block.timestamp.unixtime` | `timestamp` | Must be > 0 |
| `swaps[].account.owner.address` | `wallet` | Must differ from `swaps[].tokenAccount.mint` |
| `swaps[].tokenAccount.mint.address` | `mint` | Must be valid address |
| `swaps[].amountIn` | `qty_token` (derived) | Must be > 0 |
| `swaps[].amountOut` | (used for price) | Must be > 0 |

### Price Calculation

```python
price = (amountOut / amountIn) * SOL_USD
qty_usd = amountIn * price
```
*Assuming `amountOut` is in SOL or stablecoin relative to `amountIn`.*

### Platform Mapping

| Bitquery `dex.programId` | Internal Platform |
|--------------------------|-------------------|
| Raydium Program ID | `raydium` |
| Orca Program ID | `orca` |
| Jupiter Program ID | `jupiter` |
| *Other* | `unknown` (reject if strict) |

### Rejection Codes

- `REJECT_BITQUERY_SCHEMA_MISMATCH`: Missing required fields or invalid format.
- `REJECT_INVALID_PRICE`: Zero or negative price derived.
