# Discovery & Indexing (P0-safe)

This repo adds **non-canonical** tooling to discover traces/trades and to support **new data variables** from **new signal sources**
without changing the canonical schema or SQL/YAML/DDL.

## 1) Build indexes (optional)
Produces deterministic JSONL indexes:

```bash
python3 tools/build_trace_index.py --since "2025-01-01 00:00:00.000" --until "2025-01-02 00:00:00.000" --out artifacts/index
```

Outputs:
- `artifacts/index/trades_index.jsonl`
- `artifacts/index/signals_index.jsonl`

## 2) Discover traces/trades (live query)
Supports:
- base filters: `traced_wallet=...`, `token_mint=...`, `pool_id=...`, `chain=...`, `env=...`, `source=...`
- payload filters (new variables!): `payload.<key>=<value>` (searches `signals_raw.payload_json`)
- details filters: `details.<key>=<value>` (searches `forensics_events.details_json`)

Example:
```bash
python3 tools/discover_traces.py --since "2025-01-01 00:00:00.000" --where token_mint=So111... --where payload.strategy=v0 --json
```

Base filter mapping is defined in `configs/discovery_dimensions.yaml` (non-canonical; safe to extend).

## 3) Deterministic HTML report for evidence bundles
```bash
python3 tools/render_bundle_report.py --bundle /tmp/gmee_trace_bundle
```

Creates `report.html` at the bundle root and per-trade reports under `trades/<trade_id>/report.html`.
