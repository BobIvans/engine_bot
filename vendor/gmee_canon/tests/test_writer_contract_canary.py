from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import compute_config_hash, load_engine_config
from gmee.events import Microtick1sEvent, RpcEvent, SignalRawEvent, TradeAttemptEvent, TradeLifecycleEvent
from gmee.models import WriterContext
from gmee.writer import Tier0Writer


@pytest.mark.integration
def test_writer_can_write_synthetic_trade_and_canary_gate_still_passes(runner):
    # Arrange: fresh schema + canonical canary seed
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/canary_golden_trace.sql"))

    # Canary gate should pass before we add anything
    runner.run_sql_file(Path("scripts/canary_checks.sql"))

    engine_cfg = load_engine_config("configs/golden_exit_engine.yaml")
    ctx = WriterContext(
        env="test",
        chain="solana",
        experiment_id="exp_P0",
        config_hash=compute_config_hash(engine_cfg),
        model_version="p0",
        source="sdk_test",
        our_wallet="our_wallet_1",
        client_version="0.0.0",
        build_sha="deadbeef",
    )
    w = Tier0Writer(runner, ctx)

    # Synthetic trade with wallet that exists in canary aggregates, so profile view is populated.
    trace_id = str(uuid.uuid4())
    trade_id = str(uuid.uuid4())

    t0 = datetime(2025, 1, 1, 1, 0, 2, tzinfo=timezone.utc)
    signal_time = t0
    entry_send = t0 + timedelta(milliseconds=10)
    entry_confirm = t0 + timedelta(milliseconds=20)

    sig = SignalRawEvent(
        trace_id=trace_id,
        chain="solana",
        env="test",
        source="sdk_test",
        signal_id="sig_synth_1",
        signal_time=signal_time,
        traced_wallet="wallet_X",
        token_mint="token_A",
        pool_id="pool_1",
        confidence=0.9,
        payload_json={"synthetic": True},
    )
    w.write_signal_raw_event(sig)

    att = TradeAttemptEvent(
        trade_id=trade_id,
        trace_id=trace_id,
        stage="entry",
        our_wallet="our_wallet_1",
        nonce_u64=1,
        nonce_scope="wallet",
        nonce_value="1",
        local_send_time=entry_send,
        rpc_sent_list=["arm_A", "arm_B"],
        payload_hash="0" * 64,
        retry_count=0,
        idempotency_token="1" * 64,
    )
    attempt_id = w.write_trade_attempt_event(att)

    # Duplicate attempt insert should be idempotent (best-effort)
    attempt_id2 = w.write_trade_attempt_event(att)
    assert attempt_id2 == attempt_id

    rpc = RpcEvent(
        attempt_id=attempt_id,
        trade_id=trade_id,
        trace_id=trace_id,
        stage="entry",
        idempotency_token="2" * 64,
        rpc_arm="arm_A",
        sent_ts=entry_send,
        ok_bool=True,
        err_code="",
        confirm_quality="ok",
        first_seen_ts=entry_send + timedelta(milliseconds=1),
        first_confirm_ts=entry_confirm,
        finalized_ts=None,
        tx_sig="tx_synth_1",
        block_ref="block_1",
        finality_level="confirmed",
        reorg_depth=0,
    )
    w.write_rpc_event_event(rpc)

    life = TradeLifecycleEvent(
        trade_id=trade_id,
        trace_id=trace_id,
        traced_wallet="wallet_X",
        token_mint="token_A",
        pool_id="pool_1",
        signal_time=signal_time,
        entry_local_send_time=entry_send,
        entry_first_confirm_time=entry_confirm,
        buy_time=entry_confirm,
        buy_price_usd=1.0,
        amount_usd=10.0,
        entry_attempt_id=attempt_id,
        entry_idempotency_token="3" * 64,
        entry_nonce_u64=1,
        entry_rpc_sent_list=["arm_A", "arm_B"],
        entry_rpc_winner="arm_A",
        entry_tx_sig="tx_synth_1",
        entry_latency_ms=12,
        entry_confirm_quality="ok",
        entry_block_ref="block_1",
        liquidity_at_entry_usd=1000.0,
        fee_paid_entry_usd=0.01,
        slippage_pct=0.1,
    )
    plan = w.write_trade_with_plan_event(life, engine_cfg=engine_cfg)
    assert plan.mode in ("U", "T", "H")

    # microticks: post-entry window only
    mt = Microtick1sEvent(
        trade_id=trade_id,
        chain="solana",
        t_offset_s=1,
        ts=entry_confirm + timedelta(seconds=1),
        price_usd=1.01,
        liquidity_usd=900.0,
        volume_usd=5.0,
    )
    w.write_microtick_1s_event(mt)

    # Finally, canonical canary checks must still pass (writer must not violate global invariants)
    runner.run_sql_file(Path("scripts/canary_checks.sql"))
