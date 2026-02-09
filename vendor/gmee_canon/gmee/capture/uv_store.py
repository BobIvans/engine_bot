from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .universal_vars import UniversalVar, parse_ts


def _load_uv_file(path: Path) -> Iterable[UniversalVar]:
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield UniversalVar.from_dict(json.loads(line))


Key = Tuple[str, str, str]  # (entity_type, entity_id, var_name)


@dataclass
class UniversalVarStore:
    """In-memory index for Universal Variables.

    Designed for *small-to-medium* snapshots (trial windows). For large-scale data,
    keep UV in columnar storage and query with a proper engine.
    """

    # key -> (sorted timestamps, aligned uvs)
    _index: Dict[Key, Tuple[List[datetime], List[UniversalVar]]]

    @staticmethod
    def load(uv_paths: Iterable[Path]) -> 'UniversalVarStore':
        tmp: Dict[Key, List[Tuple[datetime, UniversalVar]]] = {}
        for p in uv_paths:
            for uv in _load_uv_file(p):
                key = (uv.entity_type, uv.entity_id, uv.var_name)
                tmp.setdefault(key, []).append((parse_ts(uv.ts), uv))

        idx: Dict[Key, Tuple[List[datetime], List[UniversalVar]]] = {}
        for key, pairs in tmp.items():
            pairs.sort(key=lambda t: t[0])
            ts_list = [t for t, _ in pairs]
            uv_list = [u for _, u in pairs]
            idx[key] = (ts_list, uv_list)
        return UniversalVarStore(_index=idx)

    def last_before(self, entity_type: str, entity_id: str, var_name: str, ts: str) -> Optional[UniversalVar]:
        key = (entity_type, entity_id, var_name)
        bucket = self._index.get(key)
        if not bucket:
            return None
        ts_list, uv_list = bucket
        target = parse_ts(ts)
        i = bisect.bisect_right(ts_list, target) - 1
        if i < 0:
            return None
        return uv_list[i]

    def latest(self, entity_type: str, entity_id: str, var_name: str) -> Optional[UniversalVar]:
        key = (entity_type, entity_id, var_name)
        bucket = self._index.get(key)
        if not bucket:
            return None
        _, uv_list = bucket
        return uv_list[-1] if uv_list else None
