-- scripts/canary_checks.sql
-- Minimal QA checks for canary trace.
-- MUST be assertive: use throwIf(...) so CI fails on drift.

-- Fixed IDs (must match scripts/canary_golden_trace.sql)
-- trace_id: 11111111-1111-1111-1111-111111111111
-- trade_id: 22222222-2222-2222-2222-222222222222
-- attempt_id: 33333333-3333-3333-3333-333333333333

-- 0) Existence checks (tables + rows)
SELECT throwIf(
  (SELECT count() FROM signals_raw WHERE trace_id = toUUID('11111111-1111-1111-1111-111111111111')) = 0,
  'canary: missing signals_raw row'
);

SELECT throwIf(
  (SELECT count() FROM trade_attempts WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')) = 0,
  'canary: missing trade_attempts row'
);

SELECT throwIf(
  (SELECT count() FROM rpc_events WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')) = 0,
  'canary: missing rpc_events rows'
);

SELECT throwIf(
  (SELECT count() FROM trades WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')) = 0,
  'canary: missing trades row'
);

SELECT throwIf(
  (SELECT count() FROM microticks_1s WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')) = 0,
  'canary: missing microticks_1s rows'
);

SELECT throwIf(
  (SELECT count() FROM latency_arm_state WHERE chain='solana') = 0,
  'canary: missing latency_arm_state seed row'
);

-- 1) Monotonicity check (entry): signal_time ≤ entry_local_send_time ≤ entry_first_confirm_time
SELECT throwIf(
  (SELECT count()
   FROM trades
   WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')
     AND signal_time <= entry_local_send_time
     AND entry_local_send_time <= entry_first_confirm_time) = 0,
  'canary: time monotonicity violated in trades'
);

-- 2) Must-log IDs present (non-empty strings where applicable)
SELECT throwIf(
  (SELECT count()
   FROM trades
   WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')
     AND trace_id = toUUID('11111111-1111-1111-1111-111111111111')
     AND length(experiment_id) > 0
     AND length(config_hash) > 0
     AND entry_attempt_id = toUUID('33333333-3333-3333-3333-333333333333')
     AND length(entry_idempotency_token) > 0) = 0,
  'canary: must-log ids missing/empty in trades'
);

SELECT throwIf(
  (SELECT count()
   FROM trade_attempts
   WHERE trade_id = toUUID('22222222-2222-2222-2222-222222222222')
     AND trace_id = toUUID('11111111-1111-1111-1111-111111111111')
     AND attempt_id = toUUID('33333333-3333-3333-3333-333333333333')
     AND length(idempotency_token) > 0
     AND length(config_hash) > 0
     AND length(experiment_id) > 0) = 0,
  'canary: must-log ids missing/empty in trade_attempts'
);

-- 3) MV produced wallet state row (quality-filtered)
SELECT throwIf(
  (SELECT count() FROM wallet_daily_agg_state WHERE chain='solana' AND wallet='wallet_X') = 0,
  'canary: mv_wallet_daily_agg_state did not produce wallet_daily_agg_state row'
);

-- 4) Deterministic profile view returns a row
SELECT throwIf(
  (SELECT count() FROM wallet_profile_30d WHERE chain='solana' AND wallet='wallet_X') = 0,
  'canary: wallet_profile_30d returned no row'
);

SELECT 1;
