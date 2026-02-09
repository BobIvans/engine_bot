# Iteration-1 Skeleton (CANON = vendor/gmee_canon)

## Quick start (P0)

```bash
# 1) Canon gates (DDL + drift + EXPLAIN + oracle)
./scripts/smoke.sh

# 2) Generate runtime engine config (CANON schema)
python3 -m integration.config_mapper

# 3) End-to-end demo: seed golden dataset → run SQL04 → emit exit_plan event
python3 -m integration.run_exit_plan --seed-golden
```

## Repo layout

- `vendor/gmee_canon/**` — CANON v23 (read-only)
- `strategy/**` — strategy docs + human-friendly config
- `integration/**` — glue code (mapper + one-shot demo)

## Notes

- The only exit-plan logic is CANON `queries/04_glue_select.sql` executed via named params.
- Iteration-1 write-back pattern: **append-only** `forensics_events(kind='exit_plan')`.
