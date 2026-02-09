from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class JsonKeyStatsGatherer:
    """Universal replicable mechanism (JSON keys) packaged as a gatherer.

    This does NOT change schema. It allows you to start collecting new variables from new sources immediately by
    putting them into payload_json/details_json.
    """
    table: str
    json_col: str
    json_key: str
    name: str = "json_key_stats"
    limit: int = 200

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        # Only allow canonical tables for safety
        if self.table not in {"signals_raw", "forensics_events"}:
            raise ValueError(f"JsonKeyStatsGatherer: unsupported table {self.table}")

        expr = f"JSONExtractString({self.json_col}, '{self.json_key}')"
        where = ["chain = {chain:String}"] if self.table == "signals_raw" else []
        params: Dict[str, Any] = {"chain": ctx.chain, "limit": int(self.limit)}
        if self.table == "signals_raw":
            where.append("env = {env:String}")
            params["env"] = ctx.env

        sql = f"""
        SELECT
          {expr} AS key_value,
          count() AS n
        FROM {self.table}
        WHERE { ' AND '.join(where) if where else '1' } AND key_value != ''
        GROUP BY key_value
        ORDER BY n DESC
        LIMIT {{limit:UInt32}}
        """
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "entity_type": f"{self.table}:{self.json_key}",
                "entity_id": r.get("key_value"),
                "n": r.get("n"),
                "chain": ctx.chain,
                "env": ctx.env,
                "json_key": self.json_key,
                "table": self.table,
            })
        return out
