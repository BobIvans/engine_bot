# P0 Repo Audit (Variant A) — integrity notes

This file exists to make it **obvious** whether any iteration accidentally dropped code or changed the canonical contract set.

## What changed between the “94KB” zip and the “56KB” zip
- No contract files were removed.
- The smaller zip is expected because the older archive contained Python bytecode caches (`__pycache__/*.pyc`) which were removed in the clean build.

## Canonical files
The following are **hard sources of truth** and must not be edited:
- `docs/SPEC.md`, `docs/DATA_MODEL.md`, `docs/CONTRACT_MATRIX.md`, `docs/RUNBOOK.md`
- `configs/golden_exit_engine.yaml`, `configs/queries.yaml`
- `schemas/clickhouse.sql`, `schemas/postgres.sql`
- `queries/01..04.sql`
- `scripts/*` (all scripts)

The expected hashes for the canonical set live in:
- `ci/canonical_sha256.txt`

Run this to verify:

```bash
sha256sum -c ci/canonical_sha256.txt
```

## Sanity checks
Recommended local checks (no code changes required):

```bash
# ensure no caches were accidentally committed into the zip
find . -name '__pycache__' -o -name '*.pyc'

# run oracle gate (requires ClickHouse)
python3 ci/oracle_glue_select_gate.py
```
