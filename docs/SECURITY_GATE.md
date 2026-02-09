# Security Gate Documentation

## Overview

The security gate is a component of the trading strategy's risk management system that validates token security data before allowing trades to proceed. It is implemented in [`integration/gates.py`](../integration/gates.py) and processed by the [`_security_gate()`](../integration/gates.py:164) function.

## Security Data Structure

Security data is stored in the `extra["security"]` field of a [`TokenSnapshot`](../integration/token_snapshot_store.py:22) object. The security data contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `is_honeypot` | `Optional[bool]` | Whether the token is a honeypot. `True` means the token is a honeypot and should be rejected. |
| `freeze_authority` | `Optional[bool]` | Whether the token has freeze authority enabled. `True` means the token can be frozen and should be rejected. |
| `mint_authority` | `Optional[bool]` | Whether the token has mint authority enabled. `True` means the token supply can be inflated and should be rejected. |
| `top_holders_pct` | `Optional[float]` | The percentage of tokens held by the top holders. Values > 50% are rejected by default. |

## Security Gate Logic

The security gate is implemented in the [`_extract_security_data()`](../integration/gates.py:57) function:

```python
def _extract_security_data(snapshot: Optional[TokenSnapshot]) -> Tuple[bool, Optional[str]]:
    """Extract and validate security data from snapshot.extra["security"].

    Returns:
        Tuple of (is_safe, reason) where:
        - is_safe: True if all security checks pass
        - reason: Optional string explaining why the check failed
    """
```

### Validation Rules

1. **Honeypot Check**: Reject if `is_honeypot` is `True`
2. **Freeze Authority Check**: Reject if `freeze_authority` is `True`
3. **Mint Authority Check**: Reject if `mint_authority` is `True`
4. **Top Holders Check**: Reject if `top_holders_pct` > 50.0%

### Edge Cases

- **No Snapshot**: If `snapshot` is `None`, the check passes (defers to other checks)
- **No Security Data**: If `snapshot.extra` is `None` or `snapshot.extra["security"]` is `None`, the check passes (defers to other checks)
- **Null Values**: `null`/`None` values for boolean fields are treated as safe (not `True`)
- **Invalid Values**: Invalid values for `top_holders_pct` are skipped (not rejected)

## Example Security Data

### Good Case (Passes All Checks)

```json
{
  "is_honeypot": false,
  "freeze_authority": null,
  "mint_authority": null,
  "top_holders_pct": 0.5
}
```

This data passes all security checks:
- `is_honeypot: false` - Not a honeypot
- `freeze_authority: null` - No freeze authority
- `mint_authority: null` - No mint authority
- `top_holders_pct: 0.5` - 0.5% < 50% threshold

### Bad Case (Honeypot Detected)

```json
{
  "is_honeypot": true,
  "freeze_authority": null,
  "mint_authority": null,
  "top_holders_pct": 0.5
}
```

This data fails the honeypot check with reason: `honeypot_fail`

### Bad Case (Freeze Authority Enabled)

```json
{
  "is_honeypot": false,
  "freeze_authority": true,
  "mint_authority": null,
  "top_holders_pct": 0.5
}
```

This data fails the freeze authority check with reason: `freeze_authority_fail`

### Bad Case (Mint Authority Enabled)

```json
{
  "is_honeypot": false,
  "freeze_authority": null,
  "mint_authority": true,
  "top_holders_pct": 0.5
}
```

This data fails the mint authority check with reason: `mint_authority_fail`

### Bad Case (Top Holders Too High)

```json
{
  "is_honeypot": false,
  "freeze_authority": null,
  "mint_authority": null,
  "top_holders_pct": 75.0
}
```

This data fails the top holders check with reason: `security_top_holders_fail`

## CSV Fixture Format

Security data can be included in token snapshot CSV files as additional columns:

```csv
mint,ts_snapshot,liquidity_usd,volume_24h_usd,spread_bps,top10_holders_pct,single_holder_pct,is_honeypot,freeze_authority,mint_authority,security_top_holders_pct
So11111111111111111111111111111111111111112,2026-01-05 09:59:59.000,50000.0,200000.0,120.0,60.0,20.0,false,null,null,0.5
```

The [`_extract_extra_data()`](../integration/token_snapshot_store.py:132) function extracts these columns and packages them into the `extra["security"]` dict.

## Configuration

The security gate can be enabled/disabled via configuration:

```yaml
token_profile:
  security:
    enabled: true  # Default: true
```

When `enabled: false`, the security gate is skipped entirely.

## Testing

A comprehensive smoke test is available at [`scripts/security_gate_smoke.sh`](../scripts/security_gate_smoke.sh) that validates:

1. Good case - all security checks pass
2. Bad case - honeypot detected
3. Bad case - freeze authority enabled
4. Bad case - mint authority enabled
5. Bad case - top holders percentage too high
6. Edge case - no security data (should pass)
7. Edge case - null snapshot (should pass)
8. Integration test - apply_gates with security data

Run the smoke test:

```bash
bash scripts/security_gate_smoke.sh
```

## Reject Reasons

The following reject reasons are defined in [`integration/reject_reasons.py`](../integration/reject_reasons.py):

- `HONEYPOT_FAIL` - Token is a honeypot
- `FREEZE_AUTHORITY_FAIL` - Token has freeze authority enabled
- `MINT_AUTHORITY_FAIL` - Token has mint authority enabled
- `SECURITY_TOP_HOLDERS_FAIL` - Top holders own > 50% of tokens

## Integration with Other Gates

The security gate is one of three gate types applied by [`apply_gates()`](../integration/gates.py:46):

1. **Token Gates** - Liquidity, volume, spread, holder distribution
2. **Security Gate** - Honeypot, freeze authority, mint authority, top holders
3. **Wallet Hard Filters** - Wallet ROI, winrate, trade count

All gates must pass for a trade to be allowed.
