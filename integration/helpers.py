"""integration/helpers.py

Codex-friendly wrappers around CLI helpers.

Why:
- Keep CLI entrypoints stable (P1 scripts).
- Also allow importing the same behavior as functions in other tooling (no subprocess).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from integration.allowlist_loader import load_allowlist
from integration.ch_client import ClickHouseConfig
from integration.write_signal import insert_signal, _utc_now_iso_ms as _signal_ts  # type: ignore
from integration.write_wallet_score import insert_wallet_score, _utc_now_iso_ms as _score_ts  # type: ignore


def load_allowlist_info(path: str) -> Tuple[list[str], str]:
    return load_allowlist(path)


def write_signal(
    *,
    traced_wallet: str,
    token_mint: str = "",
    pool_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    allowlist_path: str = "",
    require_allowlist: bool = False,
    chain: str = "solana",
    env: str = "canary",
    source: str = "wallet_copy",
    cfg: Optional[ClickHouseConfig] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = cfg or ClickHouseConfig()
    ts = _signal_ts()
    row, _ = insert_signal(
        cfg=cfg,
        chain=chain,
        env=env,
        source=source,
        traced_wallet=traced_wallet,
        token_mint=token_mint,
        pool_id=pool_id,
        ts=ts,
        trace_id="",
        signal_id="",
        payload=payload or {},
        allowlist_path=allowlist_path,
        require_allowlist=require_allowlist,
        log_allowlist_version=True,
        dry_run=dry_run,
    )
    return row


def write_wallet_score(
    *,
    traced_wallet: str,
    score: float,
    features: Optional[Dict[str, Any]] = None,
    allowlist_path: str = "",
    chain: str = "solana",
    env: str = "canary",
    cfg: Optional[ClickHouseConfig] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = cfg or ClickHouseConfig()
    ts = _score_ts()
    row, _ = insert_wallet_score(
        cfg=cfg,
        chain=chain,
        env=env,
        traced_wallet=traced_wallet,
        score=score,
        features=features or {},
        ts=ts,
        allowlist_path=allowlist_path,
        log_allowlist_version=True,
        dry_run=dry_run,
    )
    return row
