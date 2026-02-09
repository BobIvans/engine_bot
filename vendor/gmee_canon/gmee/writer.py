from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .clickhouse import ClickHouseQueryRunner
from .events import SignalRawEvent, TradeAttemptEvent, RpcEvent, TradeLifecycleEvent, Microtick1sEvent
from .forensics import emit_time_skew, emit_confirm_quality, emit_ordering_violation
from .models import ExitPlan, WriterContext
from .planner import compute_exit_plan
from .util import dt_to_ch_datetime64_3, ensure_fixed_hex64, sha256_hex, stable_json_dumps


class Tier0Writer:
    """Tier-0 writer (P0) enforcing canonical ordering + invariants.

    Ordering contract (P0):
      signals_raw → trade_attempts → rpc_events → trades → microticks_1s
    """

    def __init__(self, runner: ClickHouseQueryRunner, ctx: WriterContext) -> None:
        self.runner = runner
        self.ctx = ctx

        # EPIC 4.1: ordering guards (hard by default; set GMEE_ORDERING_MODE=soft to log forensics and stop).
        self._ordering_mode = os.getenv("GMEE_ORDERING_MODE", "hard").strip().lower()
        if self._ordering_mode not in ("hard", "soft"):
            self._ordering_mode = "hard"

        # Strict P0 invariants: these IDs/dims must be present for lifecycle logging.
        required = {
            "env": ctx.env,
            "chain": ctx.chain,
            "experiment_id": ctx.experiment_id,
            "config_hash": ctx.config_hash,
            "source": ctx.source,
            "our_wallet": ctx.our_wallet,
            "client_version": ctx.client_version,
            "build_sha": ctx.build_sha,
            "model_version": ctx.model_version,
        }
        missing = [k for k, v in required.items() if (v is None) or (str(v).strip() == "")]
        if missing:
            raise ValueError(f"WriterContext missing required fields: {missing}")

        # Enforce FixedString(64) shape early.
        self.ctx = WriterContext(
            **{**asdict(ctx), "config_hash": ensure_fixed_hex64(ctx.config_hash)}
        )

        # attempt cache: (trade_id, stage, payload_hash, nonce_scope, nonce_value) -> (attempt_id, attempt_no)
        self._attempt_cache: dict[tuple[str, str, str, str, str], tuple[str, int]] = {}

        # per-trade stage tracking
        self._stage_by_trade: dict[str, str] = {}

        self._valid_confirm_quality = {"ok", "suspect", "reorged"}

    @staticmethod
    def new_trade_id() -> str:
        """Generate a new trade_id UUID (P0 helper)."""
        return str(uuid.uuid4())

    # ---------- helpers ----------

    def _next_stage_allowed(self, trade_id: str, stage: str) -> None:
        order = ["signals_raw", "trade_attempts", "rpc_events", "trades", "microticks_1s"]
        cur = self._stage_by_trade.get(trade_id)
        if cur is None:
            # trade starts after signals_raw creation, so first expected is trade_attempts
            cur = "signals_raw"
        if stage not in order:
            raise ValueError(f"Unknown stage marker: {stage}")
        if order.index(stage) < order.index(cur):
            raise ValueError(f"Writer ordering violation: got {stage} after {cur}")
        # allow same stage multiple times (e.g. multiple rpc_events)
        self._stage_by_trade[trade_id] = stage

    def _forensics_time_skew(self, trace_id: str, trade_id: str, attempt_id: Optional[str], details: Mapping[str, Any]) -> None:
        emit_time_skew(self.runner, self.ctx, trace_id=trace_id, trade_id=trade_id, attempt_id=attempt_id, details=details)

    def _forensics_confirm_quality(self, trace_id: str, trade_id: str, attempt_id: str, confirm_quality: str, details: Mapping[str, Any]) -> None:
        emit_confirm_quality(self.runner, self.ctx, trace_id=trace_id, trade_id=trade_id, attempt_id=attempt_id, confirm_quality=confirm_quality, details=details)

    def _sha64(self, s: str) -> str:
        return sha256_hex(s.encode("utf-8"))

    def _forensics_ordering_violation(
        self,
        trace_id: Optional[str],
        trade_id: Optional[str],
        attempt_id: Optional[str],
        details: Mapping[str, Any],
    ) -> None:
        emit_ordering_violation(self.runner, self.ctx, trace_id=trace_id, trade_id=trade_id, attempt_id=attempt_id, details=details)

    def _ch_int(self, sql: str, params: Mapping[str, Any]) -> int:
        out = (self.runner.execute_raw(sql, params) or '').strip()
        if not out:
            return 0
        # ClickHouse returns a single value possibly with trailing newline
        try:
            return int(out.splitlines()[0].strip())
        except Exception:
            return 0

    def _ordering_violation(self, *, trace_id: Optional[str], trade_id: Optional[str], attempt_id: Optional[str], details: Mapping[str, Any]) -> None:
        self._forensics_ordering_violation(trace_id=trace_id, trade_id=trade_id, attempt_id=attempt_id, details=details)
        if self._ordering_mode == 'soft':
            # In soft mode we stop the downstream write to avoid partial/broken data.
            raise RuntimeError('ordering_violation (soft): downstream write skipped')
        raise RuntimeError('ordering_violation: ordering prerequisites not met')

    def _db_assert_before_trades(self, *, trace_id: str, trade_id: str, attempt_id: str) -> None:
        # DB-level assertions (EPIC 4.1): prevent silent partial traces.
        n_sig = self._ch_int('SELECT count() FROM signals_raw WHERE trace_id={trace_id:UUID}', {'trace_id': trace_id})
        n_att = self._ch_int('SELECT count() FROM trade_attempts WHERE attempt_id={attempt_id:UUID}', {'attempt_id': attempt_id})
        if n_sig < 1 or n_att < 1:
            self._ordering_violation(
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=attempt_id,
                details={
                    'stage': 'trades',
                    'signals_raw_exists': int(n_sig >= 1),
                    'trade_attempts_exists': int(n_att >= 1),
                },
            )

    def _db_assert_before_microticks(self, *, trade_id: str) -> None:
        # Ensure trade row exists and entry confirmation is ok.
        out = (self.runner.execute_raw(
            'SELECT any(entry_confirm_quality) FROM trades WHERE trade_id={trade_id:UUID}',
            {'trade_id': trade_id},
        ) or '').strip()
        if not out:
            self._ordering_violation(trace_id=None, trade_id=trade_id, attempt_id=None, details={'stage': 'microticks_1s', 'trade_exists': 0})
        if out.splitlines()[0].strip().lower() != 'ok':
            self._ordering_violation(trace_id=None, trade_id=trade_id, attempt_id=None, details={'stage': 'microticks_1s', 'entry_confirm_quality': out.strip()})

    # ---------- API ----------

    def write_signal_raw(
        self,
        *,
        source: str,
        signal_id: str,
        signal_time: datetime,
        traced_wallet: str,
        token_mint: str,
        pool_id: str,
        confidence: Optional[float] = None,
        payload_json: Any = "{}",
        ingested_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
        chain: Optional[str] = None,
        env: Optional[str] = None,
    ) -> str:
        """Write signals_raw and return canonical trace_id.

        Contract (P0): trace_id is created here.
        For deterministic replay/tests we allow passing trace_id explicitly.
        """
        if chain is not None and chain != self.ctx.chain:
            raise ValueError(f"Signal chain mismatch: ev.chain={chain!r} ctx.chain={self.ctx.chain!r}")
        if env is not None and env != self.ctx.env:
            raise ValueError(f"Signal env mismatch: ev.env={env!r} ctx.env={self.ctx.env!r}")

        tid = trace_id or str(uuid.uuid4())
        pj = payload_json if isinstance(payload_json, str) else stable_json_dumps(payload_json)
        row = {
            "trace_id": tid,
            "chain": self.ctx.chain,
            "env": self.ctx.env,
            "source": source,
            "signal_id": signal_id,
            "signal_time": dt_to_ch_datetime64_3(signal_time),
            "traced_wallet": traced_wallet,
            "token_mint": token_mint,
            "pool_id": pool_id,
            "confidence": confidence,
            "payload_json": pj,
            "ingested_at": dt_to_ch_datetime64_3(ingested_at) if ingested_at else None,
        }
        self.runner.insert_json_each_row("signals_raw", [row])
        return tid

    def get_or_create_attempt_id(
        self,
        *,
        trade_id: str,
        stage: str,
        payload_hash: str,
        nonce_scope: str,
        nonce_value: Optional[str],
    ) -> tuple[str, int]:
        """Attempt contract (P0): new attempt only if payload_hash OR nonce_scope+nonce_value OR stage changes."""
        payload_hash = ensure_fixed_hex64(payload_hash)
        nonce_value_s = "" if nonce_value is None else str(nonce_value)
        key = (trade_id, stage, payload_hash, nonce_scope, nonce_value_s)
        if key in self._attempt_cache:
            return self._attempt_cache[key]

        # Deterministic attempt_id. This guarantees the P0 contract:
        # changing payload_hash OR nonce_scope/value OR stage yields a new attempt_id.
        ns = uuid.UUID(trade_id)
        attempt_id = str(uuid.uuid5(ns, "|".join(key)))

        # If this attempt was already written earlier (e.g., process restart), reuse attempt_no.
        existing = self.runner.execute_raw(
            "SELECT any(attempt_no) FROM trade_attempts WHERE attempt_id={attempt_id:UUID}",
            params={"attempt_id": attempt_id},
        ).strip()
        if existing and existing != "0":
            attempt_no = int(existing)
            self._attempt_cache[key] = (attempt_id, attempt_no)
            return attempt_id, attempt_no

        # Otherwise, allocate next attempt_no for this trade_id based on DB state.
        max_no = self.runner.execute_raw(
            "SELECT coalesce(max(attempt_no), 0) FROM trade_attempts WHERE trade_id={trade_id:UUID}",
            params={"trade_id": trade_id},
        ).strip()
        attempt_no = int(max_no or "0") + 1

        self._attempt_cache[key] = (attempt_id, attempt_no)
        return attempt_id, attempt_no

    def write_trade_attempt(
        self,
        *,
        trade_id: str,
        trace_id: str,
        stage: str,
        our_wallet: str,
        nonce_u64: int,
        nonce_scope: str,
        nonce_value: Optional[str],
        local_send_time: datetime,
        rpc_sent_list: list[str],
        payload_hash: str,
        retry_count: int = 0,
        idempotency_token: Optional[str] = None,
    ) -> str:
        self._next_stage_allowed(trade_id, "trade_attempts")

        attempt_id, attempt_no = self.get_or_create_attempt_id(
            trade_id=trade_id,
            stage=stage,
            payload_hash=payload_hash,
            nonce_scope=nonce_scope,
            nonce_value=nonce_value,
        )

        token = ensure_fixed_hex64(idempotency_token or f"{trade_id}:{stage}:{attempt_id}")
        row = {
            "attempt_id": attempt_id,
            "trade_id": trade_id,
            "trace_id": trace_id,
            "chain": self.ctx.chain,
            "env": self.ctx.env,
            "stage": stage,
            "our_wallet": our_wallet,
            "idempotency_token": token,
            "attempt_no": int(attempt_no),
            "retry_count": int(retry_count),
            "nonce_u64": int(nonce_u64),
            "nonce_scope": nonce_scope,
            "nonce_value": nonce_value,
            "local_send_time": dt_to_ch_datetime64_3(local_send_time),
            "rpc_sent_list": rpc_sent_list,
            "payload_hash": ensure_fixed_hex64(payload_hash),
            "client_version": self.ctx.client_version,
            "build_sha": self.ctx.build_sha,
        }
        self.runner.insert_json_each_row_idempotent_token("trade_attempts", [row], token_field="idempotency_token")
        return attempt_id

    def write_rpc_event(
        self,
        *,
        attempt_id: str,
        trade_id: str,
        trace_id: str,
        stage: str,
        idempotency_token: str,
        rpc_arm: str,
        sent_ts: datetime,
        ok_bool: bool,
        err_code: str,
        confirm_quality: str,
        first_seen_ts: Optional[datetime] = None,
        first_confirm_ts: Optional[datetime] = None,
        finalized_ts: Optional[datetime] = None,
        tx_sig: Optional[str] = None,
        block_ref: Optional[str] = None,
        finality_level: Optional[str] = None,
        reorg_depth: Optional[int] = None,
    ) -> None:
        self._next_stage_allowed(trade_id, "rpc_events")

        cq = confirm_quality.lower().strip()
        if cq not in self._valid_confirm_quality:
            raise ValueError(f"confirm_quality must be one of {sorted(self._valid_confirm_quality)}; got {confirm_quality!r}")

        row = {
            "attempt_id": attempt_id,
            "trade_id": trade_id,
            "trace_id": trace_id,
            "chain": self.ctx.chain,
            "env": self.ctx.env,
            "stage": stage,
            "idempotency_token": ensure_fixed_hex64(idempotency_token),
            "rpc_arm": rpc_arm,
            "sent_ts": dt_to_ch_datetime64_3(sent_ts),
            "first_seen_ts": dt_to_ch_datetime64_3(first_seen_ts) if first_seen_ts else None,
            "first_confirm_ts": dt_to_ch_datetime64_3(first_confirm_ts) if first_confirm_ts else None,
            "finalized_ts": dt_to_ch_datetime64_3(finalized_ts) if finalized_ts else None,
            "ok_bool": 1 if ok_bool else 0,
            "err_code": err_code,
            "latency_ms": None,
            "confirm_quality": cq,
            "tx_sig": tx_sig,
            "block_ref": block_ref,
            "finality_level": finality_level,
            "reorg_depth": reorg_depth,
        }
        self.runner.insert_json_each_row_idempotent_token("rpc_events", [row], token_field="idempotency_token")

        # P0 forensics: suspect/reorged confirmations must be surfaced and excluded by quality filters.
        if cq != "ok":
            self._forensics_confirm_quality(
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=attempt_id,
                confirm_quality=cq,
                details={
                    "rpc_arm": rpc_arm,
                    "stage": stage,
                    "sent_ts": dt_to_ch_datetime64_3(sent_ts),
                    "tx_sig": tx_sig,
                    "block_ref": block_ref,
                    "finality_level": finality_level,
                    "reorg_depth": reorg_depth,
                    "ok_bool": bool(ok_bool),
                    "err_code": err_code,
                },
            )

    def write_trade_with_plan(
        self,
        *,
        trade_id: str,
        trace_id: str,
        traced_wallet: str,
        token_mint: str,
        pool_id: str,
        signal_time: datetime,
        entry_local_send_time: datetime,
        entry_first_confirm_time: datetime,
        buy_time: datetime,
        buy_price_usd: float,
        amount_usd: float,
        entry_attempt_id: str,
        entry_idempotency_token: str,
        entry_nonce_u64: int,
        entry_rpc_sent_list: list[str],
        entry_rpc_winner: str,
        entry_confirm_quality: str = "ok",
        entry_tx_sig: Optional[str] = None,
        entry_block_ref: Optional[str] = None,
        liquidity_at_entry_usd: Optional[float] = None,
        fee_paid_entry_usd: Optional[float] = None,
        slippage_pct: Optional[float] = None,
        engine_cfg: Optional[Mapping[str, Any]] = None,
    ) -> ExitPlan:
        """Write trades row with GMEE outputs filled via compute_exit_plan (P0)."""
        self._next_stage_allowed(trade_id, "trades")

        ecq = entry_confirm_quality.lower().strip()
        if ecq not in self._valid_confirm_quality:
            raise ValueError(
                f"entry_confirm_quality must be one of {sorted(self._valid_confirm_quality)}; got {entry_confirm_quality!r}"
            )

        # Invariant: canonical time monotonicity
        if not (signal_time <= entry_local_send_time <= entry_first_confirm_time):
            self._forensics_time_skew(
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=entry_attempt_id,
                details={
                    "signal_time": dt_to_ch_datetime64_3(signal_time),
                    "entry_local_send_time": dt_to_ch_datetime64_3(entry_local_send_time),
                    "entry_first_confirm_time": dt_to_ch_datetime64_3(entry_first_confirm_time),
                },
            )

        # P0 forensics: non-ok entry confirm quality must be surfaced.
        if ecq != "ok":
            self._forensics_confirm_quality(
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=entry_attempt_id,
                confirm_quality=ecq,
                details={
                    "stage": "entry",
                    "entry_first_confirm_time": dt_to_ch_datetime64_3(entry_first_confirm_time),
                    "entry_tx_sig": entry_tx_sig,
                    "entry_block_ref": entry_block_ref,
                },
            )

        if engine_cfg is None:
            raise ValueError("engine_cfg is required (loaded from configs/golden_exit_engine.yaml)")

        # Compute plan using TEMP trades snapshot (no need to pre-insert trades row)
        plan = compute_exit_plan(
            self.ctx.chain,
            trade_id,
            engine_cfg,
            runner=self.runner,
            trade_snapshot={
                "trade_id": trade_id,
                "chain": self.ctx.chain,
                "traced_wallet": traced_wallet,
                "buy_time": dt_to_ch_datetime64_3(buy_time),
                "buy_price_usd": float(buy_price_usd),
            },
        )

        # Entry latency ms
        latency_ms = int((entry_first_confirm_time - entry_local_send_time).total_seconds() * 1000)

        row = {
            # IDs/dims
            "trade_id": trade_id,
            "trace_id": trace_id,
            "experiment_id": self.ctx.experiment_id,
            "config_hash": ensure_fixed_hex64(self.ctx.config_hash),
            "env": self.ctx.env,
            "chain": self.ctx.chain,
            "source": self.ctx.source,

            # Entities
            "traced_wallet": traced_wallet,
            "our_wallet": self.ctx.our_wallet,
            "token_mint": token_mint,
            "pool_id": pool_id,

            # Time chain (entry)
            "signal_time": dt_to_ch_datetime64_3(signal_time),
            "entry_local_send_time": dt_to_ch_datetime64_3(entry_local_send_time),
            "entry_first_confirm_time": dt_to_ch_datetime64_3(entry_first_confirm_time),
            "entry_finalized_time": None,
            "buy_time": dt_to_ch_datetime64_3(buy_time),

            # Entry routing/idempotency
            "entry_attempt_id": entry_attempt_id,
            "entry_idempotency_token": ensure_fixed_hex64(entry_idempotency_token),
            "entry_nonce_u64": int(entry_nonce_u64),
            "entry_rpc_sent_list": entry_rpc_sent_list,
            "entry_rpc_winner": entry_rpc_winner,
            "entry_tx_sig": entry_tx_sig,
            "entry_latency_ms": int(latency_ms),
            "entry_confirm_quality": ecq,
            "entry_block_ref": entry_block_ref,

            # Economics
            "buy_price_usd": float(buy_price_usd),
            "amount_usd": float(amount_usd),
            "liquidity_at_entry_usd": liquidity_at_entry_usd,
            "fee_paid_entry_usd": float(fee_paid_entry_usd) if fee_paid_entry_usd is not None else None,
            "slippage_pct": float(slippage_pct) if slippage_pct is not None else None,

            # GMEE outputs
            "mode": plan.mode,
            "planned_hold_sec": int(plan.planned_hold_sec),
            "epsilon_ms": int(plan.epsilon_ms),
            "margin_mult": float(engine_cfg["chain_defaults"][self.ctx.chain]["planned_hold"]["margin_mult_default"]),
            "trailing_pct": 0.0,
            "aggr_flag": int(plan.aggr_flag),
            "planned_exit_ts": plan.planned_exit_ts,

            # Exit attempt/routing (nullable until exit)
            "exit_attempt_id": None,
            "exit_idempotency_token": None,
            "exit_nonce_u64": None,
            "exit_rpc_sent_list": [],
            "exit_rpc_winner": None,
            "exit_tx_sig": None,
            "exit_local_send_time": None,
            "exit_first_confirm_time": None,
            "exit_finalized_time": None,
            "exit_confirm_quality": None,

            # Outcome
            "sell_time": None,
            "sell_price_usd": None,
            "fee_paid_exit_usd": None,
            "hold_seconds": 0,
            "roi": 0.0,
            "success_bool": 0,
            "failure_mode": "pending",

            # Risk/vet
            "vet_pass": 1,
            "vet_flags": [],
            "mev_risk_prob": None,
            "front_run_flag": 0,

            # Tier-1 optional
            "tx_size_bytes": None,
            "dex_route": None,
            "broadcast_spread_ms": None,
            "mempool_size_at_send": None,

            # Audit
            "model_version": self.ctx.model_version,
            "build_sha": self.ctx.build_sha,
        }

        # EPIC 4.1: DB-level ordering asserts (prevent silent partial traces)
        self._db_assert_before_trades(trace_id=trace_id, trade_id=trade_id, attempt_id=entry_attempt_id)

        self.runner.insert_row_if_not_exists(
            "trades",
            row,
            exists_sql="SELECT count() FROM trades WHERE trade_id = {trade_id:UUID}",
            exists_params={"trade_id": trade_id},
        )

        # P0 forensics: if entry confirmation is suspect/reorged, surface it.
        if ecq != "ok":
            self._forensics_confirm_quality(
                trace_id=trace_id,
                trade_id=trade_id,
                attempt_id=entry_attempt_id,
                confirm_quality=ecq,
                details={
                    "stage": "entry",
                    "entry_tx_sig": entry_tx_sig,
                    "entry_block_ref": entry_block_ref,
                    "entry_first_confirm_time": dt_to_ch_datetime64_3(entry_first_confirm_time),
                },
            )
        return plan

    def write_microtick_1s(
        self,
        *,
        trade_id: str,
        t_offset_s: int,
        ts: datetime,
        price_usd: Optional[float] = None,
        liquidity_usd: Optional[float] = None,
        volume_usd: Optional[float] = None,
    ) -> None:
        self._next_stage_allowed(trade_id, "microticks_1s")

        # EPIC 4.1: DB-level ordering assert before writing microticks.
        self._db_assert_before_microticks(trade_id=trade_id)

        if price_usd is None:
            raise ValueError("microticks_1s.price_usd is required (schema Float64, not Nullable)")
        row = {
            "trade_id": trade_id,
            "chain": self.ctx.chain,
            "t_offset_s": int(t_offset_s),
            "ts": dt_to_ch_datetime64_3(ts),
            "price_usd": float(price_usd),
            "liquidity_usd": float(liquidity_usd) if liquidity_usd is not None else None,
            "volume_usd": float(volume_usd) if volume_usd is not None else None,
        }
        self.runner.insert_json_each_row("microticks_1s", [row])


    # ---------- typed event helpers (SDK-friendly) ----------

    def write_signal_raw_event(self, ev: SignalRawEvent) -> str:
        return self.write_signal_raw(
            source=ev.source,
            signal_id=ev.signal_id,
            signal_time=ev.signal_time,
            traced_wallet=ev.traced_wallet,
            token_mint=ev.token_mint,
            pool_id=ev.pool_id,
            confidence=ev.confidence,
            payload_json=ev.payload_json,
            ingested_at=ev.ingested_at,
            trace_id=ev.trace_id,
            chain=ev.chain,
            env=ev.env,
        )

    def write_trade_attempt_event(self, ev: TradeAttemptEvent) -> str:
        return self.write_trade_attempt(
            trade_id=ev.trade_id,
            trace_id=ev.trace_id,
            stage=ev.stage,
            our_wallet=ev.our_wallet,
            nonce_u64=ev.nonce_u64,
            nonce_scope=ev.nonce_scope,
            nonce_value=ev.nonce_value,
            local_send_time=ev.local_send_time,
            rpc_sent_list=ev.rpc_sent_list,
            payload_hash=ev.payload_hash,
            retry_count=ev.retry_count,
            idempotency_token=ev.idempotency_token,
        )

    def write_rpc_event_event(self, ev: RpcEvent) -> None:
        self.write_rpc_event(
            attempt_id=ev.attempt_id,
            trade_id=ev.trade_id,
            trace_id=ev.trace_id,
            stage=ev.stage,
            idempotency_token=ev.idempotency_token,
            rpc_arm=ev.rpc_arm,
            sent_ts=ev.sent_ts,
            ok_bool=ev.ok_bool,
            err_code=ev.err_code,
            confirm_quality=ev.confirm_quality,
            first_seen_ts=ev.first_seen_ts,
            first_confirm_ts=ev.first_confirm_ts,
            finalized_ts=ev.finalized_ts,
            tx_sig=ev.tx_sig,
            block_ref=ev.block_ref,
            finality_level=ev.finality_level,
            reorg_depth=ev.reorg_depth,
        )

    def write_trade_with_plan_event(self, ev: TradeLifecycleEvent, *, engine_cfg: Mapping[str, Any]) -> ExitPlan:
        return self.write_trade_with_plan(
            trade_id=ev.trade_id,
            trace_id=ev.trace_id,
            traced_wallet=ev.traced_wallet,
            token_mint=ev.token_mint,
            pool_id=ev.pool_id,
            signal_time=ev.signal_time,
            entry_local_send_time=ev.entry_local_send_time,
            entry_first_confirm_time=ev.entry_first_confirm_time,
            buy_time=ev.buy_time,
            buy_price_usd=ev.buy_price_usd,
            amount_usd=ev.amount_usd,
            entry_attempt_id=ev.entry_attempt_id,
            entry_idempotency_token=ev.entry_idempotency_token,
            entry_nonce_u64=ev.entry_nonce_u64,
            entry_rpc_sent_list=ev.entry_rpc_sent_list,
            entry_rpc_winner=ev.entry_rpc_winner,
            entry_tx_sig=ev.entry_tx_sig,
            entry_confirm_quality=ev.entry_confirm_quality,
            entry_block_ref=ev.entry_block_ref,
            liquidity_at_entry_usd=ev.liquidity_at_entry_usd,
            fee_paid_entry_usd=ev.fee_paid_entry_usd,
            slippage_pct=ev.slippage_pct,
            engine_cfg=engine_cfg,
        )

    def write_microtick_1s_event(self, ev: Microtick1sEvent) -> None:
        self.write_microtick_1s(
            trade_id=ev.trade_id,
            t_offset_s=ev.t_offset_s,
            ts=ev.ts,
            price_usd=ev.price_usd,
            liquidity_usd=ev.liquidity_usd,
            volume_usd=ev.volume_usd,
        )
