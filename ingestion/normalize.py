"""ingestion/normalize.py

Normalize raw source records into Trade / reject dicts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, Union

from ingestion.sources.base import TradeSource
from integration.trade_normalizer import normalize_trade_record
from integration.trade_types import Trade


def iter_trades(source: TradeSource) -> Iterator[Union[Trade, Dict[str, Any]]]:
    for i, rec in enumerate(source.iter_records(), start=1):
        if not isinstance(rec, dict):
            yield {"_reject": True, "lineno": i, "reason": "invalid_trade", "detail": "record_not_dict"}
            continue
        yield normalize_trade_record(rec, lineno=i)
