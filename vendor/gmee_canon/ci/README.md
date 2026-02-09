# CI helpers (P0)

This folder contains non-canonical, CI-facing helpers. Canonical artifacts live in:
- docs/, configs/, schemas/, queries/, scripts/

## Oracle expected artifact

- `oracle_expected.tsv` is the single source of truth for the expected output of `queries/04_glue_select.sql`
  on the canonical seed dataset (`scripts/seed_golden_dataset.sql`) with params from
  `configs/golden_exit_engine.yaml`.

Generate/update (when canon changes, not in P0):
```bash
python3 ci/generate_oracle_expected.py
```

## YAML-derived literal ban (second line of defense)

`yaml_literal_ban_guard.py` extracts numeric decision values from `configs/golden_exit_engine.yaml` and asserts
they do not appear as literals in `queries/04_glue_select.sql`. Primary defense remains `scripts/assert_no_drift.py`.

## Local one-button gates

Run the same P0 gates locally as in CI:

```bash
make gates
```

This starts ClickHouse via `docker-compose.yml` (if needed) and executes: DDL apply, EXPLAIN SYNTAX, anti-drift,
literal-ban guard, VIEW determinism guard, canary, oracle, and writer ordering DB-asserts guard.
