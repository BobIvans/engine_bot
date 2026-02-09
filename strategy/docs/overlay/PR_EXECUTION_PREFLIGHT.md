# PR-6.1: Execution Preflight Layer

## Overview

PR-6.1 adds an execution preflight layer for estimating execution quality metrics including fill_rate, slippage_bps, and latency_ms. This layer runs deterministically offline and provides insights into expected execution performance without requiring external API calls.

## Schema: execution_metrics.v1

```python
{
    "schema_version": "execution_metrics.v1",
    "rows_total": int,
    "candidates": int,  # BUY rows that passed gates
    "filled": int,
    "fill_rate": float,
    "latency_ms": {"p50": int, "p90": int, "max": int},
    "slippage_bps": {"avg": float, "p90": float, "max": float},
    "fill_fail_by_reason": {
        "ttl_expired": int,
        "slippage_too_high": int,
        "missing_snapshot": int,
        "missing_wallet_profile": int
    }
}
```

## Deterministic Execution Model

### Latency Model

The latency model is deterministic and uses the formula:

```
latency_ms = base_latency_ms + (lineno % (jitter_ms + 1))
```

Where:
- `base_latency_ms`: Base latency in milliseconds (configurable)
- `jitter_ms`: Maximum jitter in milliseconds (configurable)
- `lineno`: Line number in the input trades file (1-indexed)

This model ensures reproducible latency values across runs.

### Slippage Model

The slippage model is deterministic and uses the formula:

```
slippage_bps = slippage_bps_base + (size_usd * slippage_bps_per_usd)
```

Where:
- `slippage_bps_base`: Base slippage in basis points (configurable)
- `size_usd`: Trade size in USD
- `slippage_bps_per_usd`: Slippage increase per USD of size (configurable)

### Fill Gates

A BUY trade is considered a "candidate" if it has:
- Valid token snapshot (not missing_snapshot)
- Valid wallet profile (not missing_wallet_profile)

A candidate is "filled" if it passes:
- TTL gate: `latency_ms <= ttl_sec * 1000`
- Slippage gate: `slippage_bps <= max_slippage_bps`

Otherwise, the fill failure reason is recorded:
- `ttl_expired`: Latency exceeded TTL
- `slippage_too_high`: Slippage exceeded maximum
- `missing_snapshot`: Token snapshot not found
- `missing_wallet_profile`: Wallet profile not found

## Configuration

The execution_preflight section in the config YAML:

```yaml
execution_preflight:
  ttl_sec_default: 30           # Default TTL in seconds
  max_slippage_bps: 200         # Maximum allowed slippage in bps
  base_latency_ms: 100          # Base latency in ms
  jitter_ms: 50                  # Maximum jitter in ms
  slippage_bps_base: 50         # Base slippage in bps
  slippage_bps_per_usd: 0.03    # Slippage increase per USD
```

## Integration

### CLI Usage

```bash
python3 -m integration.paper_pipeline \
  --dry-run \
  --summary-json \
  --execution-preflight \
  --config integration/fixtures/config/execution_preflight.yaml \
  --trades-jsonl integration/fixtures/trades.execution_preflight.jsonl \
  --token-snapshot integration/fixtures/token_snapshot.execution_preflight.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.execution_preflight.csv
```

### Output Example

```json
{
  "ok": true,
  "execution_metrics": {
    "schema_version": "execution_metrics.v1",
    "rows_total": 2,
    "candidates": 2,
    "filled": 1,
    "fill_rate": 0.5,
    "latency_ms": {"p50": 100, "p90": 101, "max": 101},
    "slippage_bps": {"avg": 200.15, "p90": 350.0, "max": 350.0},
    "fill_fail_by_reason": {
      "ttl_expired": 0,
      "slippage_too_high": 1,
      "missing_snapshot": 0,
      "missing_wallet_profile": 0
    }
  }
}
```

## Smoke Test

Run the deterministic smoke test:

```bash
bash scripts/execution_preflight_smoke.sh
```

Expected smoke result:
- candidates: 2
- filled: 1
- fill_rate: 0.5
- slippage_too_high: 1

## Hard Rules

1. **Deterministic**: No randomness, no "now", no external calls
2. **stdout-contract**: `--summary-json` outputs exactly 1 JSON line
3. **Errors**: Stderr with `ERROR:` prefix + exit 1

## Files Modified/Created

- `integration/execution_preflight.py`: Main execution preflight module
- `integration/fixtures/trades.execution_preflight.jsonl`: Test fixtures (2 BUY trades)
- `integration/fixtures/token_snapshot.execution_preflight.csv`: Token snapshot fixtures
- `integration/fixtures/wallet_profiles.execution_preflight.csv`: Wallet profile fixtures
- `integration/fixtures/config/execution_preflight.yaml`: Configuration fixtures
- `scripts/execution_preflight_smoke.sh`: Smoke test script
- `integration/paper_pipeline.py`: Added `--execution-preflight` flag
- `scripts/overlay_lint.sh`: Added execution preflight smoke run
