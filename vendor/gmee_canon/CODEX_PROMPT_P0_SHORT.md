# Codex prompt — GMEE P0 v0.4 (Variant A)

You are implementing GMEE **P0 only**.

Forbidden: any P1/P2 (bandit/tuning jobs, epsilon-controller automation, new features/sources, tick archive beyond post-entry window).

**HARD SOURCES OF TRUTH (DO NOT EDIT):**
- `docs/SPEC.md`, `docs/DATA_MODEL.md`, `docs/CONTRACT_MATRIX.md`, `docs/RUNBOOK.md`
- `configs/golden_exit_engine.yaml`, `configs/queries.yaml`
- `schemas/clickhouse.sql`, `schemas/postgres.sql`
- `queries/01_profile_query.sql`, `queries/02_routing_query.sql`, `queries/03_microticks_window.sql`, `queries/04_glue_select.sql`
- `scripts/assert_no_drift.py`, `scripts/canary_*.sql`, `scripts/seed_golden_dataset.sql`

You may ONLY write business-code that matches those contracts.

**Do these 3 things in main-repo:**

1) Implement Tier-0 writer SDK with STRICT ordering:
`signals_raw → trade_attempts → rpc_events → trades → microticks_1s`
Always populate must-log IDs:
`trace_id, trade_id, attempt_id, idempotency_token, experiment_id, config_hash`.
Attempt_id is created at pre-sign; new attempt_id only if `payload_hash` OR (`nonce_scope`,`nonce_value`) OR `stage` changes.
`confirm_quality` is strictly: `ok|suspect|reorged`; suspect/reorged MUST NOT enter training/aggregations; anomalies go to `forensics_events`.

2) Implement `compute_exit_plan()` with 1:1 parity to `queries/04_glue_select.sql`:
- DO NOT re-implement threshold math.
- Execute `04_glue_select.sql` in ClickHouse and pass ALL placeholders using values from `configs/golden_exit_engine.yaml` (Variant A).
- Return: `mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag`.
- Writer must record these planned fields into `trades`.

3) Add CI/test gate that:
- Applies `schemas/clickhouse.sql` to a clean ClickHouse,
- Runs `scripts/seed_golden_dataset.sql`,
- Runs `queries/04_glue_select.sql` with params from YAML,
- Compares result to expected TSV **1:1**.

Note: the canonical expected TSV lives in `ci/oracle_glue_select_gate.py` and is derived from `scripts/seed_golden_dataset.sql`.
