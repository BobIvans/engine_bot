# docs/CONTRACT_MATRIX.md — SPEC ↔ DATA_MODEL ↔ DDL ↔ Queries ↔ YAML (v0.4, Variant A)

Purpose: eliminate drift by mapping every contract element to its **single source of truth**, and defining CI rules that must fail on mismatch.

Legend:
- SPEC: docs/SPEC.md
- DM: docs/DATA_MODEL.md
- DDL: schemas/clickhouse.sql / schemas/postgres.sql
- Q: queries/01..04.sql
- YAML: configs/*.yaml

---

## 1) Objects map (1:1)

| Object | SPEC | DM | DDL | Q |
|---|---|---|---|---|
| signals_raw | writer ordering + trace_id | signals_raw | clickhouse.sql:signals_raw |  |
| trade_attempts | attempt contract | trade_attempts | clickhouse.sql:trade_attempts |  |
| rpc_events | confirm_quality | rpc_events | clickhouse.sql:rpc_events | (jobs P1) |
| trades | exit_plan + outcomes | trades | clickhouse.sql:trades | 04_glue_select |
| microticks_1s | post-entry window | microticks_1s | clickhouse.sql:microticks_1s | 03_microticks_window, 04_glue_select |
| wallet_daily_agg_state | quality filter | wallet_daily_agg_state | clickhouse.sql:wallet_daily_agg_state + MV |  |
| wallet_profile_30d | canonical profile | wallet_profile_30d | clickhouse.sql:wallet_profile_30d | 01_profile_query |
| latency_arm_state | routing snapshot | latency_arm_state | clickhouse.sql:latency_arm_state | 02_routing_query |
| controller_state | tuning audit | controller_state | clickhouse.sql:controller_state |  |
| provider_usage_daily | budget gate | provider_usage_daily | clickhouse.sql:provider_usage_daily |  |
| forensics_events | anomaly log | forensics_events | clickhouse.sql:forensics_events | scripts/canary_checks.sql |
| config_store | config hash store | postgres config_store | postgres.sql:config_store |  |
| experiment_registry | reproducibility | postgres experiment_registry | postgres.sql:experiment_registry |  |
| promotions_audit | signed promotions | postgres promotions_audit | postgres.sql:promotions_audit |  |

---

## 2) YAML sources of truth

### 2.1 configs/golden_exit_engine.yaml

Single source of truth for:
- retention TTLs (**retention.…**) — *validated against DDL in CI*
- mode thresholds (`mode_thresholds_sec`)
- base quantile mapping (`base_quantile_by_mode`) — *contract asserted in CI*
- planned_hold clamp (`planned_hold.*`)
- epsilon config (`epsilon.*`)
- aggression triggers (`aggr_triggers.*`)
- microticks window (`microticks.window_sec`)
- tier1_capture gating (`tier1_capture.*`)

### 2.2 configs/queries.yaml

Single source of truth for:
- which SQL files are the “read API”
- what parameters they accept (must match placeholders in SQL)

---

## 3) Anti-drift rules (P0 hard)

This section defines the Anti-drift rules for CI (Variant A).

### 3.1 Variant A rule (parameterized glue query)

**Variant A:** `queries/04_glue_select.sql` MUST be fully parameterized.

Forbidden in SQL04:
- hardcoded numeric literals for thresholds/epsilon/aggr/clamps/retention windows

Allowed in SQL04:
- string literals `'U'|'S'|'M'|'L'`
- CASE/multiIf logic
- helper constants that are not config thresholds (e.g., 0/1 for boolean math)

CI enforces this via `scripts/assert_no_drift.py`.

---

## 4) YAML → SQL placeholder mapping (P0)

Scope: `configs/golden_exit_engine.yaml: chain_defaults.solana`

| YAML path | Meaning | SQL placeholder (queries/04_glue_select.sql) |
|---|---|---|
| mode_thresholds_sec.U | upper bound for mode U | `{mode_u_max_sec:UInt32}` |
| mode_thresholds_sec.S | upper bound for mode S | `{mode_s_max_sec:UInt32}` |
| mode_thresholds_sec.M | upper bound for mode M | `{mode_m_max_sec:UInt32}` |
| planned_hold.margin_mult_default | hold multiplier | `{margin_mult:Float32}` |
| planned_hold.clamp_sec.min_hold_sec | min hold | `{min_hold_sec:UInt32}` |
| planned_hold.clamp_sec.max_hold_sec | max hold | `{max_hold_sec:UInt32}` |
| epsilon.pad_ms_default | epsilon pad | `{epsilon_pad_ms:UInt32}` |
| epsilon.hard_bounds_ms.min | epsilon min | `{epsilon_min_ms:UInt32}` |
| epsilon.hard_bounds_ms.max | epsilon max | `{epsilon_max_ms:UInt32}` |
| aggr_triggers.U.window_s | U runaway window | `{aggr_u_window_s:UInt16}` |
| aggr_triggers.U.pct | U runaway pct | `{aggr_u_pct:Float32}` |
| aggr_triggers.S.window_s | S runaway window | `{aggr_s_window_s:UInt16}` |
| aggr_triggers.S.pct | S runaway pct | `{aggr_s_pct:Float32}` |
| aggr_triggers.M.window_s | M runaway window | `{aggr_m_window_s:UInt16}` |
| aggr_triggers.M.pct | M runaway pct | `{aggr_m_pct:Float32}` |
| aggr_triggers.L.window_s | L runaway window | `{aggr_l_window_s:UInt16}` |
| aggr_triggers.L.pct | L runaway pct | `{aggr_l_pct:Float32}` |
| microticks.window_sec | max microticks window read | `{microticks_window_s:UInt16}` |

### Mapping contract (asserted)

The base quantile mapping is a contract:

U→q10_hold_sec, S→q25_hold_sec, M→q40_hold_sec, L→median_hold_sec

- YAML must match this
- SQL must implement this (CI checks tokens)

---

## 5) YAML → DDL retention mapping (P0)

| YAML path | Meaning | DDL object |
|---|---|---|
| retention.signals_raw_ttl_days | TTL days | `signals_raw` TTL |
| retention.trade_attempts_ttl_days | TTL days | `trade_attempts` TTL |
| retention.rpc_events_ttl_days | TTL days | `rpc_events` TTL |
| retention.microticks_ttl_days | TTL days | `microticks_1s` TTL |
| retention.forensics_ttl_days | TTL days | `forensics_events` TTL |
| retention.trades_ttl_days | 0 = no TTL | `trades` TTL must be absent when 0 |

---

## 6) CI gates (P0 promotion gates)

CI must fail if any of the following is false:

1) ClickHouse DDL applies on empty DB
2) `EXPLAIN SYNTAX` compiles queries/01..04.sql
3) `scripts/assert_no_drift.py` passes:
   - YAML keys exist
   - SQL placeholders exist and match configs/queries.yaml param lists
   - Variant A: no hardcoded YAML threshold values appear as numeric literals in SQL04
   - mapping contract is present in SQL and matches YAML
   - DDL TTLs match YAML retention
4) Canary test passes:
   - seed canary trace loaded
   - canary checks run without errors
5) Oracle test passes:
   - deterministic seed dataset loaded
   - glue query output equals expected snapshot

---

## 7) Canonical writer ordering (cemented)

Writer ordering is a contract (SPEC + DM + runbook):

`signals_raw → trade_attempts → rpc_events → trades → microticks_1s`
