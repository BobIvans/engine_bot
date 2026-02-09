# Golden Mean Exit Engine (GMEE) — P0 contracts skeleton (v0.4)

This repo is a **P0 “contracts + storage + canary + CI gates”** skeleton for GMEE (mini-ML without ML).

Goal: make Codex (or any engineer) able to write business-code **without guessing** data contracts.

## P0 Scope (what we DO here)

- Canonical contracts: attempt/idempotency, confirm_quality/reorg, forensics, writer ordering
- Storage: ClickHouse DDL (tables + TTL) + minimal MV/VIEW
- Reproducibility/audit: Postgres DDL
- Canonical Read API: `queries/01..04.sql` (versioned “SQL-as-API”)
- Anti-drift: YAML ↔ SQL ↔ DDL ↔ docs gate (Variant A)
- Canary + Oracle test for `04_glue_select.sql`

## Non-goals (P0)

- Full trading execution, bandit tuning, ε-controller jobs, ML, full tick archive, lot accounting (P1+)

## Repo layout

- `docs/SPEC.md` — canonical spec (P0 invariants + contracts + gates)
- `docs/DATA_MODEL.md` — canonical Tier-0/Tier-1 schema contracts
- `docs/CONTRACT_MATRIX.md` — anti-drift map: SPEC ↔ DM ↔ DDL ↔ SQL ↔ YAML + CI rules
- `docs/RUNBOOK.md` — daily QA + canary + promotion gates (P0)
- `configs/golden_exit_engine.yaml` — engine defaults (**retention TTLs**, mode thresholds, clamp, epsilon, aggr triggers, microticks window)
- `configs/queries.yaml` — query registry (SQL-as-API + params)
- `schemas/clickhouse.sql` — executable DDL + TTL + MV + VIEW
- `schemas/postgres.sql` — config_store + experiment_registry + promotions_audit
- `queries/01..04.sql` — canonical read API
- `scripts/*` — canary seed/checks + oracle dataset + drift assertions + local smoke
- `.github/workflows/ch_compile_smoke.yml` — CI gate

## P0 Invariants (non-negotiable)

- Single truth sources must match 1:1:
  `docs/SPEC.md + docs/DATA_MODEL.md + schemas/*.sql + queries/*.sql + configs/*.yaml`
- Writer ordering (contract): `signals_raw → trade_attempts → rpc_events → trades → microticks_1s`
- `confirm_quality`: `ok|suspect|reorged` (suspect/reorged are excluded from learning aggregates and ε updates)
- MV/VIEW minimum: `mv_wallet_daily_agg_state` + `wallet_profile_30d`
- Anti-drift (Variant A): `queries/04_glue_select.sql` is parameterized by config; CI asserts no hardcoded config thresholds in SQL.

## Local quickstart (ClickHouse)

> Requires Docker.

One command:

```bash
bash scripts/local_smoke.sh
```

Manual:

```bash
docker compose up -d
docker exec -i clickhouse clickhouse-client --multiquery < schemas/clickhouse.sql

# Canary seed + checks
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_golden_trace.sql
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_checks.sql

# Oracle (deterministic)
bash scripts/oracle_test.sh
```

## CI gate (must pass)

- Apply DDL on empty ClickHouse
- Compile queries/01..04.sql (`EXPLAIN SYNTAX`)
- Pass anti-drift check (`scripts/assert_no_drift.py`)
- Pass canary seed + checks
- Pass oracle test for 04_glue_select.sql (stable output)

Not financial advice. Engineering/research scaffold only.
