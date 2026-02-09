from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..base import GatherContext

@dataclass
class WindowDeltaGatherer:
    """Generic replicable mechanism: compare a numeric metric between baseline vs recent windows.

    Works for any entity column + numeric column in an existing canonical table.
    Deterministic anchor: uses ctx.until_ts if provided, else anchors on max(time_column).
    """
    name: str = "window_delta"
    table: str = "rpc_events"
    time_column: str = "sent_ts"
    entity_type: str = "rpc_arm"
    entity_column: str = "rpc_arm"
    value_column: str = "latency_ms"
    recent_window_s: int = 3600
    baseline_window_s: int = 86400
    min_rows: int = 50
    limit_entities: int = 2000

    def _anchor(self, ctx: GatherContext) -> str:
        if ctx.until_ts:
            return ctx.until_ts
        sql = f"SELECT max({self.time_column}) AS mx FROM {self.table} WHERE chain={{chain:String}} AND env={{env:String}}"
        rows = ctx.ch.query_json(sql, params={"chain": ctx.chain, "env": ctx.env}, database=ctx.database)
        mx = rows[0].get("mx") if rows else None
        # ClickHouse may return as string; pass through as DateTime64 string
        return str(mx) if mx else "1970-01-01 00:00:00.000"

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        anchor = self._anchor(ctx)
        params: Dict[str, Any] = {
            "chain": ctx.chain,
            "env": ctx.env,
            "anchor": anchor,
            "recent_s": int(self.recent_window_s),
            "base_s": int(self.baseline_window_s),
            "min_rows": int(self.min_rows),
            "limit": int(self.limit_entities),
        }
        sql = f"""
WITH
  anchor AS toDateTime64({{anchor:String}}, 3, 'UTC'),
  recent_from AS anchor - toIntervalSecond({{recent_s:UInt32}}),
  base_from   AS anchor - toIntervalSecond({{base_s:UInt32}})
SELECT
  '{'window_delta'}' AS gatherer,
  '{{entity_type}}' AS entity_type,
  toString({self.entity_column}) AS entity_id,
  countIf({self.time_column} >= recent_from AND {self.time_column} < anchor) AS n_recent,
  countIf({self.time_column} >= base_from AND {self.time_column} < recent_from) AS n_base,
  quantileTDigestIf(0.90)({self.value_column},
    {self.time_column} >= recent_from AND {self.time_column} < anchor AND {self.value_column} IS NOT NULL) AS recent_p90,
  quantileTDigestIf(0.90)({self.value_column},
    {self.time_column} >= base_from AND {self.time_column} < recent_from AND {self.value_column} IS NOT NULL) AS base_p90,
  (recent_p90 - base_p90) AS delta_p90,
  if(base_p90>0, recent_p90/base_p90, NULL) AS ratio_p90
FROM {self.table}
WHERE chain = {{chain:String}} AND env = {{env:String}}
GROUP BY entity_id
HAVING (n_recent + n_base) >= {{min_rows:UInt32}}
ORDER BY ratio_p90 DESC NULLS LAST, n_recent DESC
LIMIT {{limit:UInt32}}
"""
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        for r in rows:
            r["entity_type"] = self.entity_type
        return rows
