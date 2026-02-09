from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class SignalSourceStatsGatherer:
    """Generic source beyond wallets: per signals_raw.source / signal_id stats (counts + confidence)."""
    name: str = "signal_source_stats"
    limit: int = 5000

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        where = ["chain = {chain:String}", "env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit)}
        if ctx.since_ts:
            where.append("signal_time >= toDateTime64({since:String}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append("signal_time < toDateTime64({until:String}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
        SELECT
          chain, env, source, signal_id,
          count() AS n,
          avgIf(confidence, confidence IS NOT NULL) AS confidence_avg,
          quantileTDigestIf(0.1)(confidence, confidence IS NOT NULL) AS confidence_p10,
          quantileTDigestIf(0.9)(confidence, confidence IS NOT NULL) AS confidence_p90
        FROM signals_raw
        WHERE {' AND '.join(where)}
        GROUP BY chain, env, source, signal_id
        ORDER BY n DESC
        LIMIT {limit:UInt32}
        """
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        for r in rows:
            r["entity_type"] = "signal_source"
            r["entity_id"] = f"{r.get('source')}|{r.get('signal_id')}"
        return rows
