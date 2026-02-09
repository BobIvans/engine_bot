from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..base import GatherContext

@dataclass
class CategoricalDistributionGatherer:
    """Config-driven top-K distribution for any categorical expression.

    Produces one row per entity_id + category value for top-K categories, plus entropy and total count in a separate summary row.

    Params:
      name, entity_type, entity_expr, from_sql, where_base, category_expr, top_k
    """
    name: str = "categorical_distribution"
    entity_type: str = "custom"
    entity_expr: str = "''"
    from_sql: str = "FROM trades t"
    where_base: List[str] = None  # type: ignore
    category_expr: str = "''"
    top_k: int = 20
    limit_entities: int = 2000
    min_rows: int = 20

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = list(self.where_base or [])
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "top_k": int(self.top_k), "limit": int(self.limit_entities), "min_rows": int(self.min_rows)}
        if ctx.since_ts:
            params["since"] = ctx.since_ts
            where.append("ts >= toDateTime64({since:DateTime64(3)}, 3, 'UTC')")
        if ctx.until_ts:
            params["until"] = ctx.until_ts
            where.append("ts < toDateTime64({until:DateTime64(3)}, 3, 'UTC')")
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""

        sql = f"""
WITH base AS (
  SELECT
    {self.entity_expr} AS entity_id,
    {self.category_expr} AS cat,
    ts
  {self.from_sql}
  {where_clause}
),
counts AS (
  SELECT entity_id, cat, count() AS c
  FROM base
  GROUP BY entity_id, cat
),
totals AS (
  SELECT entity_id, sum(c) AS n_rows
  FROM counts
  GROUP BY entity_id
),
ranked AS (
  SELECT
    c.entity_id,
    c.cat,
    c.c,
    t.n_rows,
    row_number() OVER (PARTITION BY c.entity_id ORDER BY c.c DESC, c.cat) AS rn
  FROM counts c
  INNER JOIN totals t USING(entity_id)
  WHERE t.n_rows >= {{min_rows:UInt32}}
),
entropy AS (
  SELECT
    entity_id,
    -sum( (c / n_rows) * log2(c / n_rows) ) AS entropy_bits
  FROM ranked
  GROUP BY entity_id
)
SELECT
  '{self.name}' AS gatherer,
  '{self.entity_type}' AS entity_type,
  r.entity_id,
  r.n_rows,
  e.entropy_bits,
  r.cat AS category,
  r.c AS category_count
FROM ranked r
INNER JOIN entropy e USING(entity_id)
WHERE r.rn <= {{top_k:UInt32}}
ORDER BY r.n_rows DESC, r.entity_id, r.category_count DESC
LIMIT {{limit:UInt32}}
"""
        return ctx.ch.query_json(sql, params=params, database=ctx.database)
