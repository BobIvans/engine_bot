from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class TokenPoolRegimeGatherer:
    """Generic source beyond wallets: token/pool regime signals from trades + microticks_1s.

    Uses only canonical tables (no schema changes). Produces volatility-like proxy stats and win-rate proxy if sell_price_usd exists.
    """
    name: str = "token_pool_regime"
    limit_entities: int = 2000

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = ["t.chain = {chain:String}", "t.env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit_entities)}
        if ctx.since_ts:
            where.append("t.buy_time >= toDateTime64({since:String}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append("t.buy_time < toDateTime64({until:String}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
        WITH per_trade AS (
          SELECT
            t.chain,
            t.env,
            t.token_mint,
            t.pool_id,
            t.trade_id,
            t.buy_price_usd,
            t.sell_price_usd,
            max(m.price_usd) AS max_price_usd,
            min(m.price_usd) AS min_price_usd,
            avg(m.liquidity_usd) AS avg_liquidity_usd,
            avg(m.volume_usd) AS avg_volume_usd
          FROM trades t
          LEFT JOIN microticks_1s m ON m.trade_id = t.trade_id
          WHERE {' AND '.join(where)}
          GROUP BY t.chain, t.env, t.token_mint, t.pool_id, t.trade_id, t.buy_price_usd, t.sell_price_usd
        )
        SELECT
          chain,
          env,
          token_mint,
          pool_id,
          count() AS n_trades,
          avgIf((sell_price_usd / buy_price_usd) - 1.0, sell_price_usd IS NOT NULL AND buy_price_usd > 0) AS avg_return_realized,
          avgIf((max_price_usd / buy_price_usd) - 1.0, buy_price_usd > 0 AND max_price_usd > 0) AS avg_max_runup,
          avgIf((min_price_usd / buy_price_usd) - 1.0, buy_price_usd > 0 AND min_price_usd > 0) AS avg_max_drawdown,
          avgIf(avg_liquidity_usd, avg_liquidity_usd IS NOT NULL) AS liquidity_avg_usd,
          avgIf(avg_volume_usd, avg_volume_usd IS NOT NULL) AS volume_avg_usd
        FROM per_trade
        GROUP BY chain, env, token_mint, pool_id
        ORDER BY n_trades DESC, token_mint
        LIMIT {limit:UInt32}
        """
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        for r in rows:
            r["entity_type"] = "token_pool"
            r["entity_id"] = f"{r.get('token_mint')}|{r.get('pool_id')}"
        return rows
