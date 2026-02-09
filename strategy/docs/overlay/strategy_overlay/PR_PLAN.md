> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# PR plan (P0 only) — make Codex "hit the rails"

This ordering minimizes drift risk and keeps scope strictly P0.

## PR0 — Vendor canon + lock it
- Copy canon to `vendor/gmee_canon/`.
- Add CODEOWNERS for `vendor/gmee_canon/**`.
- Add CI step `canon unchanged` (diff or checksums).

Acceptance:
- Any edit inside `vendor/gmee_canon/**` blocks the PR (unless explicitly overridden).

## PR1 — CI gates (anti-drift + canary + oracle)
- Start a clean ClickHouse in CI.
- Apply `vendor/gmee_canon/schemas/clickhouse.sql`.
- `EXPLAIN SYNTAX` compile for `vendor/gmee_canon/queries/01..04.sql`.
- Run `vendor/gmee_canon/scripts/assert_no_drift.py`.
- Run canary: `canary_golden_trace.sql` then `canary_checks.sql`.
- Run oracle: seed golden dataset then execute `queries/04_glue_select.sql` with YAML params and compare TSV 1:1.

Acceptance:
- CI is required for merge; fails on any drift.

## PR2 — ClickHouse/Postgres migrations (main-repo style)
- Integrate canon DDL into your migration mechanism (same objects, same names).

Acceptance:
- Migrations apply cleanly on empty DBs (dev + CI).

## PR3 — Query runner (registry only)
- Implement a runner that executes only named queries from `configs/queries.yaml`.
- Strict param validation: no missing/extra params.
- Use ClickHouse named params (`--param_name=value`) only (no regex placeholder rewriting).

Acceptance:
- A small test proves placeholder ↔ params 1:1.

## PR4 — Tier-0 writer (ordering contract)
- Implement writer with strict ordering: `signals_raw → trade_attempts → rpc_events → trades → microticks_1s`.
- Always write must-log IDs.
- Enforce time monotonicity; write `forensics_events(kind='time_skew')` on violations.

Acceptance:
- Canary trace passes end-to-end.

## PR5 — compute_exit_plan() = SQL parity
- No math in code.
- Execute `queries/04_glue_select.sql` via runner with params from `golden_exit_engine.yaml`.
- Return and persist: `mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag`.

Acceptance:
- SDK test matches oracle TSV 1:1.
