# Tools catalog (P0 helpers)

These helpers add reproducibility and “no guessing” guarantees without changing canonical SQL/YAML/DDL/docs/scripts.

Note on `ci/repo_audit.py`: it fails if your working tree contains Python bytecode caches (`__pycache__` / `*.pyc`). If you run any compile step locally, clean caches before `repo_audit`:

```bash
find . -name '__pycache__' -o -name '*.pyc' | xargs rm -rf
```


## Diagnostics / CI-friendly gates
- `python3 tools/gmee_doctor.py` — end-to-end local validation: audit → schema → canary → oracle → schema guard → integrity
- `python3 tools/validate_evidence_bundle.py --bundle <dir>` — verify manifest sha256 + row counts

## Evidence bundles
- `python3 tools/export_evidence_bundle.py --trade-id <UUID> --out <dir>` — trade-scope bundle
- `python3 tools/export_evidence_bundle.py --trace-id <UUID> --out <dir>` — trace-scope bundle
- `python3 tools/export_trace_bundle_from_trade.py --trade-id <UUID> --out <dir>` — resolve trace_id then export
- `python3 tools/replay_evidence_bundle.py --bundle <dir>` — replay into current CH database
- `python3 tools/replay_evidence_bundle.py --bundle <dir> --force` — delete scoped rows then replay

## Reports
- `python3 tools/trace_report.py --trace-id <UUID> --out report.json`

## Discovery & Indexing (non-canonical, P0-safe)

These tools add **generic, replicable** ways to work with **new data variables** from new sources (beyond wallets)
without changing canonical SQL/DDL/YAML:

- `tools/build_trace_index.py` — export deterministic `trades_index.jsonl` + `signals_index.jsonl` for offline search.
- `tools/discover_traces.py` — live discovery with filters:
  - base: `traced_wallet=...`, `token_mint=...`, `pool_id=...`, `source=...`, `chain=...`, `env=...`
  - new variables: `payload.<key>=...` (searches `signals_raw.payload_json`)
  - new variables: `details.<key>=...` (searches `forensics_events.details_json`)
- `tools/render_bundle_report.py` — deterministic HTML report for trade/trace evidence bundles with automatic attribute harvesting.

Config (non-canonical, safe to extend):
- `configs/discovery_dimensions.yaml` — base filter mapping (table/column/type) for discovery.


## DataGatherer
- `tools/run_datagatherers.py` — gather reproducible features to JSONL snapshots
- `tools/suggest_settings.py` — generate advisory config suggestions (does not modify YAML)

- `tools/build_feature_db.py` — merge datagatherer snapshots into a replicable feature_db (one JSONL per entity_type)

## Suggestions (rule-pack driven)
- `tools/validate_rulepack.py` — validate rule-pack YAML.
- `tools/suggest_settings.py --rule-pack ...` — produce advisory suggestions using gathered metrics.

## One-button investigations
- `tools/one_button_investigate.py --trade-id <uuid>` — trade_id → trace bundle → validate → HTML report.
- `tools/gmee_doctor.py --investigate-trade-id <uuid>` — run doctor checks then export/report.

## Feature fusion & enrichment
- `tools/fuse_snapshot.py --snapshot-dir ...` — fuse all gatherer outputs by entity.
- `tools/enrich_features.py --in <jsonl> --map <yaml> --out <jsonl>` — attach metadata from entity maps.
