# PR-8.1: Signals Dump (signals JSONL + reject_reason)

## Overview

PR-8.1 adds a deterministic "dump" of trade decisions (ENTER/SKIP) to a JSONL file for DuckDB/Parquet analysis.

## Key Features

- **Deterministic sidecar dump**: No randomness, no external API calls, no "now" timestamps
- **Atomic writes**: Uses tmp file + `os.replace` for safe file updates
- **Schema version**: `signals.v1` for DuckDB/Parquet compatibility
- **Comprehensive fields**: Captures all decision-relevant data including reject_reason

## Schema (signals.v1)

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Always `"signals.v1"` |
| `run_trace_id` | string | Unique run identifier |
| `lineno` | int | Line number in input file (0 if N/A) |
| `ts` | string | Trade timestamp |
| `wallet` | string | Trading wallet address |
| `mint` | string | Token mint address |
| `tx_hash` | string | Transaction hash (empty if N/A) |
| `mode` | string | Mode bucket (e.g., "U", "D", etc.) |
| `wallet_tier` | string\|null | Wallet tier from profile (null if N/A) |
| `decision` | string | `"ENTER"` or `"SKIP"` |
| `reject_stage` | string\|null | Stage where rejection occurred: `"normalizer"`, `"gates"`, `"sim_preflight"`, or null |
| `reject_reason` | string\|null | Canonical reject reason (see below), or null |
| `edge_bps` | int\|null | Computed edge in basis points (from +EV gate) |
| `ttl_sec` | int\|null | Time-to-live in seconds from mode config |
| `tp_pct` | float\|null | Take profit percentage from mode config |
| `sl_pct` | float\|null | Stop loss percentage from mode config |
| `sim_exit_reason` | string\|null | Simulated exit: `"TP"`, `"SL"`, `"TIME"` (only with `--signals-include-sim`) |
| `sim_pnl_usd` | float\|null | Simulated PnL in USD (only with `--signals-include-sim`) |
| `sim_roi` | float\|null | Simulated ROI (only with `--signals-include-sim`) |

## Reject Reasons

### Normalizer Stage
- `invalid_trade` - Trade record failed validation

### Token Gates Stage
- `missing_snapshot` - Token snapshot not available
- `min_liquidity_fail` - Liquidity below threshold
- `min_volume_24h_fail` - 24h volume below threshold
- `max_spread_fail` - Spread exceeds threshold
- `top10_holders_fail` - Top 10 holders concentration too high
- `single_holder_fail` - Single holder concentration too high

### Wallet Hard Filters
- `wallet_min_winrate_fail` - Wallet winrate below threshold
- `wallet_min_roi_fail` - Wallet ROI below threshold
- `wallet_min_trades_fail` - Wallet trade count below threshold

### Sim Preflight (+EV Gate)
- `missing_snapshot` - Token snapshot required for +EV calculation
- `missing_wallet_profile` - Wallet profile required for +EV calculation
- `ev_below_threshold` - Edge in bps below `min_edge_bps` threshold

## CLI Usage

```bash
# Basic signals dump
python3 -m integration.paper_pipeline \
  --trades-jsonl trades.jsonl \
  --signals-out signals.jsonl

# With simulation results
python3 -m integration.paper_pipeline \
  --trades-jsonl trades.jsonl \
  --signals-out signals.jsonl \
  --sim-preflight \
  --signals-include-sim
```

## File Format

JSONL (JSON Lines) - one JSON object per line:

```jsonl
{"schema_version":"signals.v1","run_trace_id":"paper_abc123","lineno":1,"ts":"2024-01-01T00:00:00","wallet":"Wallet1","mint":"MintA","tx_hash":"tx123","mode":"U","wallet_tier":"gold","decision":"ENTER","reject_stage":null,"reject_reason":null,"edge_bps":25,"ttl_sec":60,"tp_pct":0.05,"sl_pct":-0.05}
{"schema_version":"signals.v1","run_trace_id":"paper_abc123","lineno":2,"ts":"2024-01-01T00:01:00","wallet":"Wallet2","mint":"MintB","tx_hash":"tx456","mode":"U","wallet_tier":null,"decision":"SKIP","reject_stage":"gates","reject_reason":"min_liquidity_fail","edge_bps":null,"ttl_sec":60,"tp_pct":0.05,"sl_pct":-0.05,"sim_exit_reason":null,"sim_pnl_usd":null,"sim_roi":null}
```

## DuckDB Integration

```sql
-- Load signals dump into DuckDB
CREATE TABLE signals AS SELECT * FROM read_json_auto('signals.jsonl');

-- Analyze decisions by mode
SELECT mode, decision, count(*) as count
FROM signals
GROUP BY mode, decision;

-- Analyze reject reasons
SELECT reject_stage, reject_reason, count(*) as count
FROM signals
WHERE decision = 'SKIP'
GROUP BY reject_stage, reject_reason
ORDER BY count DESC;
```

## Implementation Details

### Atomic Write

The signals dump uses atomic file replacement to ensure consistency:

```python
def write_signals_jsonl_atomic(path: str, rows: list[dict]) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(...)
    try:
        with os.fdopen(tmp_fd, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        os.replace(tmp_path, path)  # Atomic on POSIX
    except Exception:
        os.unlink(tmp_path)
        raise
```

### Determinism Guarantees

1. **No external calls**: All data comes from input files and local caches
2. **No timestamps**: Uses trade timestamps, not current time
3. **No randomness**: All calculations are deterministic
4. **Deterministic tick ordering**: Future ticks are sorted by timestamp

## Related Documentation

- [PR_SIM_PREFLIGHT.md](./PR_SIM_PREFLIGHT.md) - Sim preflight (+EV gate) details
- [PR_DAILY_METRICS.md](./PR_DAILY_METRICS.md) - Daily metrics aggregation
- [RELEASE.md](./RELEASE.md) - Release procedures
