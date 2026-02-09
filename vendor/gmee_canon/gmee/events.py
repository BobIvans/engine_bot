from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Literal

from .util import dt_to_ch_datetime64_3, ensure_fixed_hex64

ConfirmQuality = Literal["ok", "suspect", "reorged"]
Stage = Literal["entry", "exit"]


@dataclass(frozen=True)
class SignalRawEvent:
    trace_id: str
    chain: str
    env: str
    source: str
    signal_id: str
    signal_time: datetime
    traced_wallet: str
    token_mint: str
    pool_id: str
    confidence: float
    payload_json: Mapping[str, Any]
    ingested_at: Optional[datetime] = None

    def to_row(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "chain": self.chain,
            "env": self.env,
            "source": self.source,
            "signal_id": self.signal_id,
            "signal_time": dt_to_ch_datetime64_3(self.signal_time),
            "traced_wallet": self.traced_wallet,
            "token_mint": self.token_mint,
            "pool_id": self.pool_id,
            "confidence": float(self.confidence),
            "payload_json": __import__("json").dumps(self.payload_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "ingested_at": dt_to_ch_datetime64_3(self.ingested_at) if self.ingested_at else None,
        }


@dataclass(frozen=True)
class TradeAttemptEvent:
    trade_id: str
    trace_id: str
    stage: Stage
    our_wallet: str
    nonce_u64: int
    nonce_scope: str
    nonce_value: Optional[str]
    local_send_time: datetime
    rpc_sent_list: list[str]
    payload_hash: str
    retry_count: int = 0
    idempotency_token: Optional[str] = None  # if None writer generates

    def normalized_payload_hash(self) -> str:
        return ensure_fixed_hex64(self.payload_hash)

    def normalized_idempotency_token(self) -> Optional[str]:
        return ensure_fixed_hex64(self.idempotency_token) if self.idempotency_token else None


@dataclass(frozen=True)
class RpcEvent:
    attempt_id: str
    trade_id: str
    trace_id: str
    stage: Stage
    idempotency_token: str
    rpc_arm: str
    sent_ts: datetime
    ok_bool: bool
    err_code: str
    confirm_quality: ConfirmQuality
    first_seen_ts: Optional[datetime] = None
    first_confirm_ts: Optional[datetime] = None
    finalized_ts: Optional[datetime] = None
    tx_sig: Optional[str] = None
    block_ref: Optional[str] = None
    finality_level: Optional[str] = None
    reorg_depth: Optional[int] = None


@dataclass(frozen=True)
class TradeLifecycleEvent:
    trade_id: str
    trace_id: str
    traced_wallet: str
    token_mint: str
    pool_id: str
    signal_time: datetime
    entry_local_send_time: datetime
    entry_first_confirm_time: datetime
    buy_time: datetime
    buy_price_usd: float
    amount_usd: float
    entry_attempt_id: str
    entry_idempotency_token: str
    entry_nonce_u64: int
    entry_rpc_sent_list: list[str]
    entry_rpc_winner: str
    entry_tx_sig: str
    entry_latency_ms: int
    entry_confirm_quality: ConfirmQuality
    entry_block_ref: Optional[str] = None
    liquidity_at_entry_usd: float = 0.0
    fee_paid_entry_usd: Optional[float] = None
    slippage_pct: Optional[float] = None


@dataclass(frozen=True)
class Microtick1sEvent:
    trade_id: str
    chain: str
    t_offset_s: int
    ts: datetime
    price_usd: float
    liquidity_usd: float
    volume_usd: float

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "chain": self.chain,
            "t_offset_s": int(self.t_offset_s),
            "ts": dt_to_ch_datetime64_3(self.ts),
            "price_usd": float(self.price_usd),
            "liquidity_usd": float(self.liquidity_usd),
            "volume_usd": float(self.volume_usd),
        }
