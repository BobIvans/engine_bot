# docs/DATA_MODEL.md — GMEE (v0.4, canonical, P0)

Purpose: single source of truth for must-log data contracts, so that:
- any run is reproducible (config_hash + seed + dataset snapshot + artifacts)
- latency/ε and wallet quantiles are computed from clean subsets
- reorg/suspect confirmations do not poison metrics

---

## Global invariants (P0)

### Time (UTC)

All time columns: `DateTime64(3,'UTC')`.

Minimum monotonic chain (entry; exit analogous):

`signal_time <= entry_local_send_time <= entry_first_confirm_time (<= entry_finalized_time?)`

Violation → `forensics_events(kind='time_skew')` and `failure_mode='time_skew'`.

### IDs

- `trace_id UUID` — signal → attempts → rpc_events → trades → microticks → audit
- `trade_id UUID` — lifecycle (entry+exit)
- `attempt_id UUID` — one attempt (fanout + retries, unchanged payload)
- `idempotency_token FixedString(64)` — sha256(...) stable within attempt
- `config_hash FixedString(64)` — sha256(normalized YAML)
- `experiment_id UUID` — simulation/paper/live run id

### Units

- `*_ms` UInt32, `*_sec` UInt32/UInt16
- `*_pct` Float32 where 0.10 = 10%
- `price_usd` Float64

### Tier-0 vs Tier-1

- Tier-0: required for P0 gates and future tuning
- Tier-1: optional nullable observability, gated by `tier1_capture.enabled`

---

## ClickHouse tables (P0)

### signals_raw (append-only)

Must: `trace_id, chain, env, source, signal_id, signal_time, traced_wallet, token_mint, pool_id, confidence?, payload_json, ingested_at`

Keys: PARTITION `(chain, YYYYMM(signal_time))`, ORDER `(chain, signal_time, source, signal_id)`

Retention: TTL ~180d

### trade_attempts (append-only, P0-critical)

Must: `attempt_id, trade_id, trace_id, chain, env, stage, our_wallet, idempotency_token, attempt_no, retry_count, nonce_scope, nonce_value?, payload_hash, local_send_time, rpc_sent_list, client_version, build_sha`

Retention: TTL ~90d

### rpc_events (append-only)

Must: `attempt_id, trade_id, trace_id, chain, env, stage, idempotency_token, rpc_arm, sent_ts,
first_seen_ts?, first_confirm_ts?, finalized_ts?, ok_bool, err_code, latency_ms?,
confirm_quality, tx_sig?, block_ref?, finality_level?, reorg_depth?`

Retention: TTL ~90d

### trades (append-only, 1 row = lifecycle)

Tier-0 core:

- IDs/dims: `trade_id, trace_id, experiment_id, config_hash, env, chain, source`
- Entities: `traced_wallet, our_wallet, token_mint, pool_id`
- Entry time chain: `signal_time, entry_local_send_time, entry_first_confirm_time, entry_finalized_time?`
- Entry routing/idempotency: `entry_attempt_id, entry_idempotency_token, entry_nonce_u64, entry_rpc_sent_list, entry_rpc_winner, entry_tx_sig?, entry_latency_ms, entry_confirm_quality, entry_block_ref?`
- Economics: `buy_time, buy_price_usd, amount_usd, liquidity_at_entry_usd?, fee_paid_entry_usd?, slippage_pct?`
- GMEE outputs: `mode, planned_hold_sec, epsilon_ms, margin_mult, trailing_pct, aggr_flag, planned_exit_ts`
- Exit (nullable until exit): `exit_* times/attempt/rpc winner/confirm_quality`
- Outcome: `sell_time?, sell_price_usd?, fee_paid_exit_usd?, hold_seconds, roi, success_bool, failure_mode`
- Risk/vet: `vet_pass, vet_flags[], mev_risk_prob?, front_run_flag`

Tier-1 optional nullable:
`tx_size_bytes, dex_route, broadcast_spread_ms, mempool_size_at_send`

Retention: long (no TTL in P0; keep as long as possible)

### microticks_1s (append-only, post-entry window only)

Must: `trade_id, chain, t_offset_s, ts, price_usd, liquidity_usd?, volume_usd?`

Rule: only `t_offset_s ∈ [0..window_sec]` (config)

Retention: TTL ~60d

### wallet_daily_agg_state (AggregatingMergeTree)

Dims: `chain, wallet, day`

States:
- count trades
- wins
- tDigest quantiles hold: q10/q25/q40/median
- avg/var hold, avg/var roi

### wallet_profile_30d (VIEW)

Profile window is anchored to wallet’s `max(day)` in `wallet_daily_agg_state`:
“last 30 days relative to last observed activity” (deterministic for oracle tests).

### latency_arm_state (snapshots)

Must: `chain, rpc_arm, snapshot_ts, q90_latency_ms, ewma_mean_ms, ewma_var_ms2, epsilon_ms, a_success, b_success, degraded, cooldown_until?, reason?, config_hash`

Retention: long

### controller_state (snapshots)

Must: `chain, key, ts, value_json, config_hash, approved_by?, ticket_ref?`

Retention: long

### provider_usage_daily (budget gate)

Must: `day, provider, chain, calls, errors, cost_usd_est, budget_usd, throttled`

### forensics_events (append-only, P0-critical)

Must: `event_id, ts, chain, env, trace_id?, trade_id?, attempt_id?,
kind(time_skew|suspect_confirm|reorg|partial_confirm|schema_mismatch|other),
severity(info|warn|crit), details_json`

Retention: TTL ~180d

---

## Minimal MV/VIEW (P0)

Exactly two:

1) `mv_wallet_daily_agg_state` (trades → wallet_daily_agg_state) with strict quality filter:

`success_bool=1 AND failure_mode='none' AND hold_seconds>0 AND entry_confirm_quality='ok'`

2) `wallet_profile_30d` view (anchored window)

---

## Postgres (P0)

- `config_store`: config_hash → normalized YAML
- `experiment_registry`: reproducible runs (seed, dataset snapshot, artifact uri, metrics)
- `promotions_audit`: signed GO/NO_GO/ROLLBACK
