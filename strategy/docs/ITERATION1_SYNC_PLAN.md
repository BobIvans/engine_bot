# Iteration-1 Sync Plan — Strategy Pack ↔ Mini-ML Engine (GMEE CANON v23) v0.3

**North Star:** make Iteration-1 runnable end-to-end **without drift**.

## Definition of Done (P0)

The following commands must be green locally and in CI:

```bash
./scripts/smoke.sh
python integration/config_mapper.py
python integration/run_exit_plan.py --seed-golden
```

## Rules (non-negotiable)

1) **Single source of truth**
- `vendor/gmee_canon/**` = GMEE CANON v23 (read-only)
- strategy documents and integration code must not copy/modify CANON SQL/DDL/configs

2) **Single execution path (CI == local)**
- No alternative runners, no duplicated “oracle tests”, no divergent smoke scripts

3) **No SQL templating**
- Forbidden: `sed`, regex-based SQL rendering, string replacement in SQL files
- Allowed: ClickHouse named params (`param_<name>`) + registry-driven param validation

4) **Iteration-1 write-back pattern is fixed**
- Exit plan is written only as `forensics_events(kind='exit_plan')`
- Do not update `trades` planned_* columns in Iteration-1

5) **Golden seed is mandatory for the demo**
- Do not hand-insert wide `trades` rows. Use the CANON seed SQL.

---

## Deliverables

### D0 — Repo layout (no second canon)
**Target tree:**

- `vendor/gmee_canon/` (CANON v23, read-only)
- `strategy/` (human configs, allowlists, docs)
- `integration/` (glue code: mapper + runner)
- `scripts/` (smoke entrypoints)

Acceptance:
- LEGACY_PATH: no `golden-engine-exit/**` outside vendor
- no duplicate copies of CANON SQL/DDL/configs

### D1 — One smoke path (local == CI)
Implement `scripts/smoke.sh` as the only smoke entrypoint.

Must run (in order):
1) start ClickHouse (docker compose)
2) apply CANON DDL
3) `vendor/gmee_canon/scripts/assert_no_drift.py`
4) `python vendor/gmee_canon/ci/explain_syntax_gate.py`
5) `python vendor/gmee_canon/ci/oracle_glue_select_gate.py`

Acceptance:
- `./scripts/smoke.sh` exits 0 on success and non-zero on failure
- CI calls `./scripts/smoke.sh` (not bespoke steps)

### D2 — Config mapper (strategy → runtime CANON cfg)
Implement `integration/config_mapper.py`.

Responsibilities:
- read `strategy/strategy.yaml` (human-friendly)
- generate `integration/runtime/golden_exit_engine.yaml` (CANON schema)
- build SQL04 params strictly matching registry:
  `vendor/gmee_canon/configs/queries.yaml → functions.glue_select.params`

Acceptance:
- `python integration/config_mapper.py` exits 0 and prints a short summary
- missing/extra registry params hard-fail

### D3 — One-shot demo (seed → SQL04 → exit_plan)
Implement `integration/run_exit_plan.py --seed-golden`.

Responsibilities:
- apply DDL
- run `vendor/gmee_canon/scripts/seed_golden_dataset.sql`
- call `queries/04_glue_select.sql` via CANON runner with named params
- write back plan as `forensics_events(kind='exit_plan')`

Acceptance:
- prints one TSV row with 6 columns (CANON oracle format)
- inserts one `exit_plan` forensics event

---

## Guardrails (cheap drift checks)

- `git grep -n "\bsed\b"` must not match any CI/smoke/oracle scripts
- `find . -name "__pycache__" -o -name "*.pyc" -o -name ".pytest_cache"` must be empty in committed artifacts

