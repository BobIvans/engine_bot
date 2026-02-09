-- scripts/seed_golden_dataset.sql
-- Deterministic tiny dataset for oracle test of queries/04_glue_select.sql
--
-- Target IDs
-- trade_id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
-- traced_wallet: wallet_oracle
--
-- Safe to re-run locally:
TRUNCATE TABLE latency_arm_state;
TRUNCATE TABLE trades;
TRUNCATE TABLE microticks_1s;
TRUNCATE TABLE wallet_daily_agg_state;

-- 1) routing snapshot (single arm, deterministic epsilon=100ms)
INSERT INTO latency_arm_state
(chain, rpc_arm, snapshot_ts, q90_latency_ms, ewma_mean_ms, ewma_var_ms2, epsilon_ms, a_success, b_success, degraded, cooldown_until, reason, config_hash)
VALUES
('solana', 'rpc_arm_oracle', toDateTime64('2025-01-01 00:00:00',3,'UTC'),
 150, 120.0, 25.0, 100, 10.0, 2.0, 0, NULL, 'oracle_seed',
 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee');

-- 2) history trades to build wallet_profile (hold_seconds constant => deterministic quantiles)
-- Insert 3 completed lifecycles that pass MV quality filter.
INSERT INTO trades (
  trade_id, trace_id, experiment_id, config_hash, env, chain, source,
  traced_wallet, our_wallet, token_mint, pool_id,
  signal_time, entry_local_send_time, entry_first_confirm_time, entry_finalized_time, buy_time,
  entry_attempt_id, entry_idempotency_token, entry_nonce_u64, entry_rpc_sent_list, entry_rpc_winner, entry_tx_sig, entry_latency_ms, entry_confirm_quality, entry_block_ref,
  buy_price_usd, amount_usd, liquidity_at_entry_usd, fee_paid_entry_usd, slippage_pct,
  mode, planned_hold_sec, epsilon_ms, margin_mult, trailing_pct, aggr_flag, planned_exit_ts,
  exit_attempt_id, exit_idempotency_token, exit_nonce_u64, exit_rpc_sent_list, exit_rpc_winner, exit_tx_sig, exit_local_send_time, exit_first_confirm_time, exit_finalized_time, exit_confirm_quality,
  sell_time, sell_price_usd, fee_paid_exit_usd, hold_seconds, roi, success_bool, failure_mode,
  vet_pass, vet_flags, mev_risk_prob, front_run_flag,
  tx_size_bytes, dex_route, broadcast_spread_ms, mempool_size_at_send,
  model_version, build_sha
) VALUES
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','bbbbbbbb-0000-0000-0000-000000000001','bbbbbbbb-0000-0000-0000-000000000002',
 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','sim','solana','oracle_seed',
 'wallet_oracle','our_wallet_A','token_hist','pool_hist',
 toDateTime64('2025-01-01 00:00:00',3,'UTC'), toDateTime64('2025-01-01 00:00:01',3,'UTC'), toDateTime64('2025-01-01 00:00:02',3,'UTC'), NULL, toDateTime64('2025-01-01 00:00:02',3,'UTC'),
 'bbbbbbbb-0000-0000-0000-000000000003',
 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
 0, ['rpc_arm_oracle'],'rpc_arm_oracle','tx_hist_1',100,'ok','slot_hist',
 1.0, 10.0, 100000.0, 0.1, 0.01,
 'U', 20, 250, 1.0, 0.0, 0, toDateTime64('2025-01-01 00:00:21.750',3,'UTC'),
 NULL,NULL,NULL,[], NULL, NULL, NULL, NULL, NULL, NULL,
 toDateTime64('2025-01-01 00:00:22',3,'UTC'), 1.1, 0.1, 20, 0.1, 1, 'none',
 1, ['ok'], NULL, 0,
 NULL,NULL,NULL,NULL,
 'gmee-v0.4','oracle'),
('cccccccc-cccc-cccc-cccc-cccccccccccc','cccccccc-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000002',
 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','sim','solana','oracle_seed',
 'wallet_oracle','our_wallet_A','token_hist','pool_hist',
 toDateTime64('2025-01-01 00:10:00',3,'UTC'), toDateTime64('2025-01-01 00:10:01',3,'UTC'), toDateTime64('2025-01-01 00:10:02',3,'UTC'), NULL, toDateTime64('2025-01-01 00:10:02',3,'UTC'),
 'cccccccc-0000-0000-0000-000000000003',
 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
 0, ['rpc_arm_oracle'],'rpc_arm_oracle','tx_hist_2',100,'ok','slot_hist',
 1.0, 10.0, 100000.0, 0.1, 0.01,
 'U', 20, 250, 1.0, 0.0, 0, toDateTime64('2025-01-01 00:10:21.750',3,'UTC'),
 NULL,NULL,NULL,[], NULL, NULL, NULL, NULL, NULL, NULL,
 toDateTime64('2025-01-01 00:10:22',3,'UTC'), 1.1, 0.1, 20, 0.1, 1, 'none',
 1, ['ok'], NULL, 0,
 NULL,NULL,NULL,NULL,
 'gmee-v0.4','oracle'),
('dddddddd-dddd-dddd-dddd-dddddddddddd','dddddddd-0000-0000-0000-000000000001','dddddddd-0000-0000-0000-000000000002',
 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','sim','solana','oracle_seed',
 'wallet_oracle','our_wallet_A','token_hist','pool_hist',
 toDateTime64('2025-01-01 00:20:00',3,'UTC'), toDateTime64('2025-01-01 00:20:01',3,'UTC'), toDateTime64('2025-01-01 00:20:02',3,'UTC'), NULL, toDateTime64('2025-01-01 00:20:02',3,'UTC'),
 'dddddddd-0000-0000-0000-000000000003',
 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
 0, ['rpc_arm_oracle'],'rpc_arm_oracle','tx_hist_3',100,'ok','slot_hist',
 1.0, 10.0, 100000.0, 0.1, 0.01,
 'U', 20, 250, 1.0, 0.0, 0, toDateTime64('2025-01-01 00:20:21.750',3,'UTC'),
 NULL,NULL,NULL,[], NULL, NULL, NULL, NULL, NULL, NULL,
 toDateTime64('2025-01-01 00:20:22',3,'UTC'), 1.1, 0.1, 20, 0.1, 1, 'none',
 1, ['ok'], NULL, 0,
 NULL,NULL,NULL,NULL,
 'gmee-v0.4','oracle');

-- 3) target trade (entry exists; not counted in MV because hold_seconds=0)
INSERT INTO trades (
  trade_id, trace_id, experiment_id, config_hash, env, chain, source,
  traced_wallet, our_wallet, token_mint, pool_id,
  signal_time, entry_local_send_time, entry_first_confirm_time, entry_finalized_time, buy_time,
  entry_attempt_id, entry_idempotency_token, entry_nonce_u64, entry_rpc_sent_list, entry_rpc_winner, entry_tx_sig, entry_latency_ms, entry_confirm_quality, entry_block_ref,
  buy_price_usd, amount_usd, liquidity_at_entry_usd, fee_paid_entry_usd, slippage_pct,
  mode, planned_hold_sec, epsilon_ms, margin_mult, trailing_pct, aggr_flag, planned_exit_ts,
  exit_attempt_id, exit_idempotency_token, exit_nonce_u64, exit_rpc_sent_list, exit_rpc_winner, exit_tx_sig, exit_local_send_time, exit_first_confirm_time, exit_finalized_time, exit_confirm_quality,
  sell_time, sell_price_usd, fee_paid_exit_usd, hold_seconds, roi, success_bool, failure_mode,
  vet_pass, vet_flags, mev_risk_prob, front_run_flag,
  tx_size_bytes, dex_route, broadcast_spread_ms, mempool_size_at_send,
  model_version, build_sha
) VALUES
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','sim','solana','oracle_seed',
 'wallet_oracle','our_wallet_A','token_target','pool_target',
 toDateTime64('2025-01-01 01:00:00',3,'UTC'), toDateTime64('2025-01-01 01:00:01',3,'UTC'), toDateTime64('2025-01-01 01:00:02',3,'UTC'), NULL, toDateTime64('2025-01-01 01:00:02',3,'UTC'),
 'aaaaaaaa-0000-0000-0000-000000000003',
 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
 0, ['rpc_arm_oracle'],'rpc_arm_oracle','tx_target',100,'ok','slot_target',
 1.0, 10.0, 100000.0, 0.1, 0.01,
 'U', 0, 0, 1.0, 0.0, 0, toDateTime64('2025-01-01 01:00:00',3,'UTC'),
 NULL,NULL,NULL,[], NULL, NULL, NULL, NULL, NULL, NULL,
 NULL, NULL, NULL, 0, 0.0, 0, 'none',
 1, ['ok'], NULL, 0,
 NULL,NULL,NULL,NULL,
 'gmee-v0.4','oracle');

-- 4) microticks for target trade (entry price 1.00, max within 12s = 1.04 => aggr_flag=1 for U)
INSERT INTO microticks_1s
(trade_id, chain, t_offset_s, ts, price_usd, liquidity_usd, volume_usd)
VALUES
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'solana', 0,  toDateTime64('2025-01-01 01:00:02',3,'UTC'), 1.00, 100000.0, 1000.0),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'solana', 10, toDateTime64('2025-01-01 01:00:12',3,'UTC'), 1.04, 100000.0, 2000.0);
