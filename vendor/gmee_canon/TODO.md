# P0 Board (v0.4) — Final status

## P0 Definition of Done (DoD)

- ✅ Single truth sources aligned: SPEC ↔ DATA_MODEL ↔ DDL ↔ queries ↔ YAML
- ✅ Empty ClickHouse: DDL applies cleanly
- ✅ Canonical queries compile (`EXPLAIN SYNTAX`): `queries/01..04.sql`
- ✅ Anti-drift gate passes (YAML↔SQL↔DDL↔docs)
- ✅ Oracle dataset: `04_glue_select.sql` returns expected stable output
- ✅ Canary trace: writer ordering tables have consistent rows; no forensics spikes

## What to do next

- See `P0_FINAL_TASKS.md` for the merge/pull-in task list into the main repo.

## Out of scope (P1+)

- writer/ingest service implementation (beyond minimal Tier-0 loggers)
- ε-controller, bandit routing updates, breaker automation
- real chain/testnet integration, scheduled QA pipelines
- tuning thresholds / P1/P2 strategy
