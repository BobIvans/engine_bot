# Golden Mean Exit Engine (GMEE) — SPEC (v0.4, canonical, P0)

Goal: **mini-ML without ML** exit planner + data/ops skeleton so we can:
- log must-have data from day 1
- run reproducible sim/paper/live later
- tune later (P1/P2) without data archaeology

## Scope (P0)

P0 fixes **interfaces and truth sources**:
- attempt/idempotency/nonce/concurrency contracts
- confirm/reorg/partial-confirm policy and quality tags
- must-log schema (ClickHouse) + reproducibility/audit (Postgres)
- canonical read API: `queries/01..04.sql`
- canary + oracle + CI anti-drift gates

Non-goals (P0): ML, full tick archive, full routing/bandit tuning, lot accounting.

---

## Engine contract (P0)

GMEE produces an `exit_plan` (logged into `trades`):
- `mode` ∈ {U,S,M,L}
- `planned_hold_sec`
- `epsilon_ms`
- `planned_exit_ts`
- `aggr_flag`

Plus audit: `config_hash`, `experiment_id`, build/version, routing snapshot reference.

---

## P0 definitions (must match DATA_MODEL/DDL/queries/YAML)

### hold_seconds (temporary P0 definition)

`hold_seconds = exit_first_confirm_time - entry_first_confirm_time`

- P0 treats one `trades` row as one “position lifecycle”.
- Lot accounting is P1.

### Quality filter (wallet aggregates + ε learning)

Only these trades feed `wallet_daily_agg_state`:

`success_bool=1 AND failure_mode='none' AND entry_confirm_quality='ok' AND hold_seconds>0`

### Canonical enums

- `env`: `sim|paper|live|canary|testnet`
- `stage`: `entry|exit`
- `confirm_quality`: `ok|suspect|reorged`
- `mode`: `U|S|M|L`
- `failure_mode`: `none|rpc_error|latency_timeout|slippage_exceed|mev|rug|reorg|time_skew|data_bad|unknown`

---

## Attempt / Confirm / Forensics contract (P0)

### IDs (single source of truth)

- `trace_id`: created on signal ingest (`signals_raw`) and lives through entire lifecycle
- `trade_id`: created when lifecycle is created (entry intent)
- `attempt_id`: created on **pre-sign** (before RPC send)
- `idempotency_token`: fixed within attempt; changes only if payload/nonce/stage changes
- `config_hash`: sha256(normalized YAML)

### Attempt definition

Attempt = one logical attempt to perform `entry` or `exit` for a given `trade_id`,
including multi-RPC fanout and network retries, **as long as tx payload is unchanged**.

Create a **new attempt_id** if any changes:
1) `payload_hash` (instructions/params/signature),
2) `nonce_scope + nonce_value` changes actual tx (e.g. Solana blockhash / EVM nonce),
3) `stage` changes (entry vs exit).

### confirm_quality

We tag confirmations so we **don’t learn on garbage**:
- `ok`: reliable inclusion/commitment per chain policy → allowed for latency/ε and wallet aggregates
- `suspect`: seen on some RPC/ws, but no reliable inclusion within timeout OR conflicting answers → **must NOT** feed learning/aggregates
- `reorged`: previously ok, later rolled back → exclude from learning; log forensics

`first_confirm_time` = first time it became `ok`.
`finalized_time` (optional) = finality time (if supported).

### Writer ordering (P0 required)

1) `signals_raw` (trace_id)
2) `trade_attempts` (attempt_id + idempotency_token + payload_hash + rpc_sent_list + local_send_time)
3) `rpc_events` (per-arm observations, confirm_quality, latency_ms, tx_sig, block_ref)
4) `trades` (1 row lifecycle: planned_* + outcome)
5) `microticks_1s` (only after entry ok, post-entry window [0..window_sec])

### forensics_events (when to write)

Write `forensics_events` for anything that breaks trust in metrics:
- `time_skew`: monotonic chain violated
- `suspect_confirm`: long seen-not-included / conflicting RPC answers
- `reorg`: ok → reorged
- `partial_confirm`: entry ok but exit not (or vice versa) after SLO
- `schema_mismatch`: Tier-0 missing/null spikes, query/DDL mismatch

---

## Canonical read API (SQL-as-API)

These SQL files are treated as a versioned API:
- `queries/01_profile_query.sql`: wallet profile summary
- `queries/02_routing_query.sql`: latest per-arm routing snapshot
- `queries/03_microticks_window.sql`: microticks window
- `queries/04_glue_select.sql`: debug exit-plan computation (parameterized by config)

---

## Anti-drift rule (P0)

- Config thresholds live in `configs/golden_exit_engine.yaml`
- `queries/04_glue_select.sql` must be **fully parameterized** for:
  - mode thresholds + base quantile mapping
  - epsilon pad + clamp bounds
  - aggression trigger windows + pct
  - planned_hold clamp bounds (min/max)
- CI must fail if:
  - placeholders are missing
  - SQL contains hardcoded literals equal to config thresholds
  - `configs/queries.yaml` params do not match SQL placeholders
