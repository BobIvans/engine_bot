"""integration/trade_types.py

Small, strategy-owned (integration/**) contracts used by Iteration-1 pipeline.

These are intentionally minimal and do NOT redefine CANON schemas.

## Canonical JSONL contract (one line = one trade event)

Required fields:
- ts: ISO-8601 / 'YYYY-MM-DD HH:MM:SS[.mmm]' or unix sec/ms (UTC preferred)
- wallet: string (base58)
- mint: string (base58)
- side: BUY/SELL (or buy/sell; normalizer will canonicalize)
- price: float > 0 (USD)
- size_usd: float > 0 (USD)

Optional fields:
- platform: raydium|jupiter|pumpfun|meteora|other
- tx_hash: string
- pool_id: string
- slot: int
- size_token: float
- source: string (heluis/dune/manual/etc.)

Normalizer behavior (P0):
- invalid JSON -> reject invalid_json
- missing required -> reject missing_field:<name>
- bad side -> reject bad_side
- non-positive price/size_usd -> reject non_positive_value
- extra fields -> ignored

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Trade:
    """Normalized copy-trade event.

    This is the minimal input the paper pipeline expects (P0).

    Notes:
    - token snapshot fields are optional; when missing, gates may be skipped.
    - all numeric fields should be floats/ints already (pipeline is tolerant).
    """

    ts: str
    wallet: str
    mint: str
    side: str  # "buy" | "sell"
    price: float = 0.0
    size_usd: float = 0.0
    platform: str = ""
    tx_hash: str = ""
    pool_id: str = ""

    # Optional enrichment snapshot (gates/features)
    liquidity_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    spread_bps: Optional[float] = None
    honeypot_pass: Optional[bool] = None

    # Optional wallet metrics (hard filters/features)
    wallet_roi_30d_pct: Optional[float] = None
    wallet_winrate_30d: Optional[float] = None
    wallet_trades_30d: Optional[int] = None

    extra: Optional[Dict[str, Any]] = None
