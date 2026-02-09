from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..base import GatherContext

@dataclass
class NumericQuantilesGatherer:
    """Config-driven quantiles over any numeric expression for any entity grouping.

    P0-safe: reads only canonical tables/columns. Useful for new sources/variables without schema changes.

    Params:
      name: output gatherer name
      entity_type: logical entity type (e.g. rpc_arm|token_mint|pool_id|source|custom)
      entity_expr: SQL expression for entity id (e.g. t.token_mint, r.rpc_arm, s.source)
      from_sql: SQL FROM/JOIN clause starting with FROM ...
      where_base: list of SQL predicates (strings) with placeholders {chain:String},{env:String},{since:DateTime64(3)},{until:DateTime64(3)}
      value_expr: numeric SQL expression to quantify
      quantiles: list of float quantiles (0..1)
      limit_entities: cap entities by count (optional)
    """
    name: str = "numeric_quantiles"
    entity_type: str = "custom"
    entity_expr: str = "''"
    from_sql: str = "FROM trades t"
    where_base: List[str] = None  # type: ignore
    value_expr: str = "0"
    quantiles: List[float] = None  # type: ignore
    limit_entities: int = 2000
    min_rows: int = 20

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = list(self.where_base or [])
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit_entities), "min_rows": int(self.min_rows)}
        if ctx.since_ts:
            params["since"] = ctx.since_ts
            where.append("ts >= toDateTime64({since:DateTime64(3)}, 3, 'UTC')")
        if ctx.until_ts:
            params["until"] = ctx.until_ts
            where.append("ts < toDateTime64({until:DateTime64(3)}, 3, 'UTC')")

        # We support a conventional alias 'ts' in from_sql. Callers can project ts via subquery.
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        # Build quantile aggregations deterministically
        qs = self.quantiles or [0.5, 0.9]
        q_exprs = ",\n       ".join([f"quantileTDigest({q})(val) AS q_{str(q).replace('.','_')}" for q in qs])

        sql = f"""
WITH base AS (
  SELECT
    {self.entity_expr} AS entity_id,
    toDateTime64(0,3,'UTC') AS dummy,
    val,
    ts
  FROM (
    SELECT
      {self.entity_expr} AS entity_id,
      {self.value_expr} AS val,
      ts
    {self.from_sql}
  )
  {where_clause}
)
SELECT
  '{self.name}' AS gatherer,
  '{self.entity_type}' AS entity_type,
  entity_id,
  count() AS n_rows,
  {q_exprs},
  avg(val) AS mean,
  min(val) AS min_v,
  max(val) AS max_v
FROM base
GROUP BY entity_id
HAVING n_rows >= {{min_rows:UInt32}}
ORDER BY n_rows DESC
LIMIT {{limit:UInt32}}
"""
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        return rows
