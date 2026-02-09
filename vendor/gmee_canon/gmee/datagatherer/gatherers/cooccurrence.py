from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class CooccurrenceGatherer:
    """Generic replicable mechanism: joint distribution of two categorical variables.

    Useful for new sources: (source x err_code), (rpc_arm x confirm_quality), etc.
    """
    name: str = "cooccurrence"
    table: str = "rpc_events"
    left_column: str = "rpc_arm"
    right_column: str = "err_code"
    time_column: str = "sent_ts"
    top_k: int = 2000

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = ["chain = {chain:String}", "env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "k": int(self.top_k)}
        if ctx.since_ts:
            where.append(f"{self.time_column} >= toDateTime64({{since:String}}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append(f"{self.time_column} < toDateTime64({{until:String}}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
WITH base AS (
  SELECT
    toString({self.left_column}) AS left_key,
    toString({self.right_column}) AS right_key,
    count() AS n
  FROM {self.table}
  WHERE {' AND '.join(where)}
  GROUP BY left_key, right_key
),
left_tot AS (
  SELECT left_key, sum(n) AS left_n FROM base GROUP BY left_key
),
right_tot AS (
  SELECT right_key, sum(n) AS right_n FROM base GROUP BY right_key
)
SELECT
  '{'cooccurrence'}' AS gatherer,
  'pair' AS entity_type,
  concat(left_key, '||', right_key) AS entity_id,
  left_key,
  right_key,
  n,
  left_n,
  right_n,
  n / nullIf(left_n, 0) AS p_right_given_left,
  n / nullIf(right_n, 0) AS p_left_given_right
FROM base
INNER JOIN left_tot USING (left_key)
INNER JOIN right_tot USING (right_key)
ORDER BY n DESC
LIMIT {{k:UInt32}}
"""
        return ctx.ch.query_json(sql, params=params, database=ctx.database)
