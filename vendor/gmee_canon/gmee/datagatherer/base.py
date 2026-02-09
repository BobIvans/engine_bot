from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol

class ClickHouseLike(Protocol):
    def query_tsv(self, sql: str, params: Optional[Dict[str, Any]] = None, database: Optional[str] = None) -> str: ...
    def query_json(self, sql: str, params: Optional[Dict[str, Any]] = None, database: Optional[str] = None) -> List[Dict[str, Any]]: ...

@dataclass(frozen=True)
class GatherContext:
    """Runtime context for gatherers.

    Do NOT mutate canonical YAML/SQL/DDL here. Gatherers only read ClickHouse and output features.
    """
    ch: ClickHouseLike
    engine_cfg: Dict[str, Any]              # parsed configs/golden_exit_engine.yaml
    env: str
    chain: str
    database: Optional[str] = None
    since_ts: Optional[str] = None          # ISO-ish string, UTC
    until_ts: Optional[str] = None          # ISO-ish string, UTC

class DataGatherer(Protocol):
    name: str
    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        """Return list of feature rows (JSON-serializable dicts)."""
        ...
