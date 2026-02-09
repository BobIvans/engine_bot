# P0 Parallel Iteration Tasks Implemented (v0.4 Variant A)

Scope: **P0 only** (no P1/P2 features). Canon files were not modified.

## 1) Idempotent write wrapper (best-effort)
- Added retry + idempotent helpers in `gmee/clickhouse.py`:
  - transient HTTP/transport retries in `execute_raw`
  - `insert_json_each_row_idempotent_token(...)` for tables with `idempotency_token`
  - `insert_row_if_not_exists(...)` for tables keyed by `trade_id` (e.g. `trades`)
- Writer now uses idempotent insertion for:
  - `trade_attempts`, `rpc_events` (token-based)
  - `trades` (trade_id existence check)

## 2) Writer contract integration test using canonical canary gate
- `tests/test_writer_contract_canary.py`:
  - applies `schemas/clickhouse.sql`
  - runs `scripts/canary_golden_trace.sql`
  - runs `scripts/canary_checks.sql` (gate)
  - writes a synthetic trade through SDK writer (strict ordering)
  - runs `scripts/canary_checks.sql` again

## 3) Strict typed event models (dataclasses)
- `gmee/events.py` provides typed inputs for Tier-0 writer:
  - `SignalRawEvent`, `TradeAttemptEvent`, `RpcEvent`, `TradeLifecycleEvent`, `Microtick1sEvent`
- Writer exposes `write_*_event(...)` helpers.

## 4) Runtime contract assertions (startup guard)
- `gmee/runtime.py` provides:
  - registry↔SQL placeholder parity check for **all** queries
  - heuristic deterministic guard for `wallet_profile_30d` (no now()/today() anchor)
  - optional `config_hash` consistency check
- `GMEE.from_env(..., validate_contracts=True)` enables this by default.

## 5) Unified forensics helper
- `gmee/forensics.py` centralizes:
  - `time_skew`
  - `suspect_confirm` / `reorg`
  - `schema_mismatch`
- Writer routes forensics emission through this helper.

