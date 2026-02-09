from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class SignalQualityGatherer:
    """Quality stats per signal source (wallet-agnostic).

    Joins signals_raw -> trades via trace_id.
    """
    name: str = "signal_quality"
    limit_sources: int = 2000
    min_trades: int = 5

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = ["s.chain = {chain:String}", "s.env = {env:String}", "t.chain = {chain:String}", "t.env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit_sources), "min_trades": int(self.min_trades)}
        if ctx.since_ts:
            where.append("s.signal_time >= toDateTime64({since:DateTime64(3)}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append("s.signal_time < toDateTime64({until:DateTime64(3)}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
WITH joined AS (
  SELECT
    s.source AS source,
    t.trade_id AS trade_id,
    t.entry_latency_ms AS entry_latency_ms,
    t.entry_confirm_quality AS entry_q
  FROM signals_raw s
  INNER JOIN trades t ON s.trace_id = t.trace_id
  WHERE {' AND '.join(where)}
)
SELECT
  '{'signal_quality'}' AS gatherer,
  'source' AS entity_type,
  source AS entity_id,
  countDistinct(trade_id) AS n_trades,
  avg(entry_latency_ms) AS latency_mean_ms,
  quantileTDigest(0.9)(entry_latency_ms) AS latency_p90_ms,
  sum(entry_q = 'ok') / count() AS ok_rate,
  sum(entry_q != 'ok') / count() AS bad_rate
FROM joined
GROUP BY source
HAVING n_trades >= {{min_trades:UInt32}}
ORDER BY n_trades DESC
LIMIT {{limit:UInt32}}
"""
        return ctx.ch.query_json(sql, params=params, database=ctx.database)
