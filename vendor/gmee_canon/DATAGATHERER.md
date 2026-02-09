# DataGatherer (mini-ML without ML) — P0-safe

This repo keeps the *planner logic* in canonical SQL (`queries/04_glue_select.sql`).
DataGatherer is a **read-only** analytics layer that:
- gathers reproducible features from canonical tables/views,
- builds a local “database of gatherers” as JSONL snapshots,
- produces **advisory** suggestions for config refresh (does NOT auto-tune or write YAML).

## Why “Golden Ratio”
We use golden-ratio conjugate **α ≈ 0.618** as a stable smoothing factor:
- it is deterministic,
- it dampens oscillations,
- it is simple enough for P0 (no ML training jobs).

## Key idea: replicate wallet infra for new sources
Wallet infra already exists via `wallet_profile_30d`.
For any new data variable/source (e.g. rpc_arm, signal source, token/pool, arbitrary JSON keys):
1) add a gatherer in `configs/datagatherers.yaml`,
2) run `tools/run_datagatherers.py`,
3) run `tools/suggest_settings.py` to get advisory patch suggestions.

## Add new variables without schema changes
Two universal mechanisms already present:
- JSON keys: `payload.<key>` and `details.<key>` via `JsonKeyStatsGatherer`
- discovery dimensions registry: `configs/discovery_dimensions.yaml`

Two additional generic mechanisms introduced:
- EntityKeyspaceGatherer: treat any existing column as an entity keyspace (token_mint, pool_id, rpc_arm, source…)
- SuggestionEngine: rule-based, golden-ratio smoothed suggestions (advisory only)
