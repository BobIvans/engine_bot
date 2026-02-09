from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class VolatilityRegimeGatherer:
    """Volatility/liquidity regime per token/pool using only post-entry microticks_1s.

    This is wallet-agnostic and works for new sources that affect token/pool selection.
    Joins microticks_1s -> trades by trade_id to get token_mint/pool_id.
    """
    name: str = "volatility_regime"
    limit_entities: int = 2000
    min_trades: int = 5

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = ["t.chain = {chain:String}", "t.env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit_entities), "min_trades": int(self.min_trades)}
        if ctx.since_ts:
            where.append("t.buy_time >= toDateTime64({since:DateTime64(3)}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append("t.buy_time < toDateTime64({until:DateTime64(3)}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
WITH mt AS (
  SELECT
    t.token_mint AS token_mint,
    t.pool_id AS pool_id,
    t.trade_id AS trade_id,
    m.price_usd AS price_usd,
    m.liquidity_usd AS liquidity_usd,
    m.volume_usd AS volume_usd
  FROM microticks_1s m
  INNER JOIN trades t ON m.trade_id = t.trade_id
  WHERE {' AND '.join(where)}
),
per_trade AS (
  SELECT
    token_mint,
    pool_id,
    trade_id,
    (max(price_usd) - min(price_usd)) / nullIf(min(price_usd), 0) AS pct_range,
    avgOrNull(liquidity_usd) AS liq_avg,
    sumOrNull(volume_usd) AS vol_sum
  FROM mt
  GROUP BY token_mint, pool_id, trade_id
),
per_entity AS (
  SELECT
    token_mint,
    pool_id,
    count() AS n_trades,
    quantileTDigest(0.5)(pct_range) AS pct_range_p50,
    quantileTDigest(0.9)(pct_range) AS pct_range_p90,
    avgOrNull(liq_avg) AS liq_avg,
    quantileTDigest(0.9)(vol_sum) AS vol_sum_p90
  FROM per_trade
  GROUP BY token_mint, pool_id
  HAVING n_trades >= {{min_trades:UInt32}}
)
SELECT
  '{'volatility_regime'}' AS gatherer,
  'token_pool' AS entity_type,
  concat(token_mint, '|', pool_id) AS entity_id,
  n_trades,
  pct_range_p50,
  pct_range_p90,
  liq_avg,
  vol_sum_p90
FROM per_entity
ORDER BY n_trades DESC, pct_range_p90 DESC
LIMIT {{limit:UInt32}}
"""
        return ctx.ch.query_json(sql, params=params, database=ctx.database)
