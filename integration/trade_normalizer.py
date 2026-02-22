"""integration/trade_normalizer.py

Normalize/validate replay inputs into Trade contracts.

Input:
  - JSONL where each non-comment line is a JSON object.
  - Supports optional enrichment fields (liquidity_usd, spread_bps, honeypot_pass, wallet_* metrics)
    for deterministic offline tests.

Output:
  - Trade objects (for valid lines)
  - Reject dicts (for invalid lines) so the pipeline can count failures.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Iterator, Optional, Tuple, Union

from .trade_types import Trade
from .reject_reasons import INVALID_TRADE


Reject = Dict[str, Any]


def load_trades_jsonl(path: str) -> Iterator[Union[Trade, Reject]]:
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            yield parse_trade_line(line=line, lineno=lineno)


def parse_trade_line(line: str, lineno: int = 0) -> Union[Trade, Reject]:
    try:
        obj = json.loads(line)
    except Exception as e:
        return _reject(lineno, INVALID_TRADE, f"json_parse_error:{e}")

    return normalize_trade_record(obj, lineno=lineno)


def normalize_trade_record(obj: Dict[str, Any], lineno: int = 0) -> Union[Trade, Reject]:
    """Normalize a dict-like trade record (from JSONL, Parquet, etc.) into Trade."""

    # Preserve optional mode tag without affecting schema. This enables
    # mode_counts metrics in the paper pipeline. We store it in Trade.extra and
    # also attach it to reject dicts for consistent bucketing.
    incoming_mode = obj.get("mode")
    if isinstance(incoming_mode, str):
        incoming_mode = incoming_mode.strip() or None
    else:
        incoming_mode = None

    def _rej(reason: str, detail: str) -> Reject:
        r = _reject(lineno, reason, detail)
        if incoming_mode is not None:
            r["mode"] = incoming_mode
        return r

    # Required fields
    missing = [k for k in ("ts", "wallet", "mint", "side", "price", "size_usd", "platform", "tx_hash") if k not in obj]
    if missing:
        return _rej(INVALID_TRADE, f"missing_fields:{','.join(missing)}")

    side = str(obj.get("side")).strip().lower()
    if side in {"buy", "b"}:
        side_norm = "BUY"
    elif side in {"sell", "s"}:
        side_norm = "SELL"
    else:
        return _rej(INVALID_TRADE, f"bad_side:{side}")

    ts = str(obj.get("ts") or "").strip()
    if not ts:
        return _rej(INVALID_TRADE, "bad_ts:empty")

    price = _opt_float(obj.get("price"))
    if price is None or price <= 0:
        return _rej(INVALID_TRADE, f"bad_price:{obj.get('price')!r}")

    size_usd = _opt_float(obj.get("size_usd"))
    if size_usd is None or size_usd <= 0:
        return _rej(INVALID_TRADE, f"bad_size_usd:{obj.get('size_usd')!r}")

    extra = obj.get("extra") if isinstance(obj.get("extra"), dict) else None
    if incoming_mode is not None:
        if extra is None:
            extra = {}
        extra["mode"] = incoming_mode

    t = Trade(
        ts=ts,
        wallet=str(obj.get("wallet")),
        mint=str(obj.get("mint")),
        side=side_norm,
        price=price,
        size_usd=size_usd,
        platform=str(obj.get("platform")),
        tx_hash=str(obj.get("tx_hash")),
        pool_id=str(obj.get("pool_id") or ""),
        # Optional enrichment
        liquidity_usd=_opt_float(obj.get("liquidity_usd")),
        volume_24h_usd=_opt_float(obj.get("volume_24h_usd")),
        spread_bps=_opt_float(obj.get("spread_bps")),
        honeypot_pass=_opt_bool(obj.get("honeypot_pass")),
        wallet_roi_30d_pct=_opt_float(obj.get("wallet_roi_30d_pct")),
        wallet_winrate_30d=_opt_float(obj.get("wallet_winrate_30d")),
        wallet_trades_30d=_opt_int(obj.get("wallet_trades_30d")),
        extra=extra,
    )
    return t


def _reject(lineno: int, reason: str, detail: str) -> Reject:
    return {"_reject": True, "lineno": lineno, "reason": reason, "detail": detail}


def _opt_float(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def _opt_int(x: Any) -> Optional[int]:
    if x is None or x == "":
        return None
    try:
        return int(x)
    except Exception:
        return None


def _opt_bool(x: Any) -> Optional[bool]:
    if x is None or x == "":
        return None
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return None


# Backward/forward-compat alias expected by tools/tune_strategy.py
def normalize_trade(*args, **kwargs):
    return normalize_trade_record(*args, **kwargs)
