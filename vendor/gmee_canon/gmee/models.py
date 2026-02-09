from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExitPlan:
    """GMEE exit plan output (P0)."""
    mode: str
    planned_hold_sec: int
    epsilon_ms: int
    planned_exit_ts: str  # ClickHouse DateTime64(3) rendered as string
    aggr_flag: int


@dataclass(frozen=True)
class WriterContext:
    env: str
    chain: str
    experiment_id: str
    config_hash: str
    model_version: str
    source: str
    our_wallet: str
    client_version: str
    build_sha: str
