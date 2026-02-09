# Data Contract Map — Strategy ↔ GMEE CANON v23 v0.5

This document maps **strategy ingestion + execution** to the **CANON ClickHouse tables**.

Core principle: **write as little as possible**, but write it **consistently** so runs are reproducible.

## P0 invariants

- **`trace_id` is present on every row we write** (signals → attempts → rpc → trades → forensics).
- **Exit plan is computed only by CANON SQL04** and written back **only as** `forensics_events(kind='exit_plan', ...)` in Iteration-1.
- No alternative SQL compilation paths (no `sed`, no string templating).

## Naming conventions

- `env`: `canary|sim|paper|live`
- `chain`: `solana`
- `source`: `wallet_copy`
- `kind` in `forensics_events`: `exit_plan|wallet_score|wallet_allowlist|run_meta|error`

---

## 1) `signals_raw` — strategy signals (entry triggers)

**Purpose:** record every candidate entry signal deterministically.

### MUST fields
- `trace_id` (UUID)
- `chain` (String) = `solana`
- `env` (String)
- `source` (String) = `wallet_copy`
- `signal_id` (String) — **stable deterministic id** (recommended: sha256(traced_wallet + token_mint + signal_time_ms))
- `signal_time` (DateTime64(3))
- `traced_wallet` (String)
- `token_mint` (String)
- `pool_id` (String)

### SHOULD fields
- `confidence` (Nullable Float32) — if present, 0..1
- `raw_json` (String/JSON) — raw payload as received (only if cheap)

---

## 2) `trade_attempts` — attempted entry execution

**Purpose:** audit and correlate what we tried to execute on-chain.

### MUST fields
- `trace_id`
- `chain`, `env`
- `entry_attempt_id` (UUID)
- `entry_idempotency_token` (FixedString / String)
- `entry_local_send_time` (DateTime64(3))

### SHOULD fields
- `traced_wallet`, `token_mint`, `pool_id` (to avoid extra joins)
- `entry_params_json` (slippage, size, route hints)

---

## 3) `rpc_events` — RPC telemetry

**Purpose:** explain execution quality and failures.

### MUST fields
- `trace_id`
- `entry_attempt_id`
- provider
- latency
- status

### SHOULD fields
- error_code / error_class
- request_id / tx_signature (if available)

---

## 4) `trades` — trade outcome + linkage

**Purpose:** store the canonical trade record.

### MUST fields (minimum for correlation)
- `trade_id` (UUID/String)
- `trace_id`
- `chain`, `env`
- `token_mint`, `pool_id`
- `traced_wallet`
- timestamps that CANON expects (signal/buy/confirm/finalize as applicable)

### P0 note
In Iteration-1, we do **not** update `trades` with planned_* exit columns. We only emit the exit plan into `forensics_events(kind='exit_plan')`.

---

## 5) `microticks_1s` — post-entry micro price ticks

**Purpose:** provide a small post-entry window for exit computation/debug.

### MUST fields
- `trade_id`
- timestamp
- price/return snapshot (whatever CANON schema defines)

### P0 rule
Only write ticks in the post-entry window:
- `[buy_time, buy_time + microticks.window_sec]`

---

## 6) `forensics_events` — everything needed for reproducibility

**Purpose:** append-only event stream for run metadata, exit plans, scoring, and debugging.

### MUST fields
- `trace_id` (or at least `trade_id` if trace_id is not available for that event)
- `chain`, `env`
- `event_time` (DateTime64(3))
- `kind` (String)
- `details_json` (String/JSON)

### Required event kinds

#### A) `exit_plan`
Write-back pattern for P0.

Recommended `details_json` keys:
- `trade_id`
- `mode`
- `planned_hold_sec`
- `epsilon_ms`
- `planned_exit_ts`
- `aggr_flag`
- `engine_cfg_hash` (sha256 of runtime `golden_exit_engine.yaml`)
- `queries_registry_hash` (sha256 of `configs/queries.yaml`)

#### B) `wallet_allowlist` (P0)
Log which allowlist was used so results can be reproduced.

Recommended `details_json` keys:
- `allowlist_uri` (path or version label)
- `allowlist_sha256`
- `wallet_count`

Write once per run (or when allowlist changes).

#### C) `wallet_score` (P1)
Only after Iteration-1 is green.

Recommended `details_json` keys:
- `model_version`
- `features` (small snapshot)
- `score`

#### D) `run_meta` / `error`
Use for environment metadata and failures:
- git commit, docker image versions, provider settings, exception traces

