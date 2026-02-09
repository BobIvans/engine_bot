"""ingestion/sources/jsonl_source.py

Offline JSONL source.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator

from ingestion.sources.base import TradeSource


class JsonlSource(TradeSource):
    def __init__(self, path: str):
        self.path = path

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
