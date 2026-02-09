from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from ..base import GatherContext

@dataclass
class RpcArmStatsGatherer:
    """Generic source beyond wallets: per rpc_arm quality/latency stats from rpc_events."""
    name: str = "rpc_arm_stats"

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        # Use sent_ts window if provided, else use entire table
        where = ["chain = {chain:String}", "env = {env:String}"]
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env}
        if ctx.since_ts:
            where.append("sent_ts >= toDateTime64({since:String}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            where.append("sent_ts < toDateTime64({until:String}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
        SELECT
          chain,
          env,
          rpc_arm,
          count() AS n,
          avgIf(latency_ms, latency_ms IS NOT NULL) AS latency_avg_ms,
          quantileTDigestIf(0.50)(latency_ms, latency_ms IS NOT NULL) AS latency_p50_ms,
          quantileTDigestIf(0.90)(latency_ms, latency_ms IS NOT NULL) AS latency_p90_ms,
          quantileTDigestIf(0.99)(latency_ms, latency_ms IS NOT NULL) AS latency_p99_ms,
          avg(ok_bool) AS ok_rate,
          avg(confirm_quality = 'suspect') AS suspect_rate,
          avg(confirm_quality = 'reorged') AS reorg_rate,
          avg(err_code != '') AS err_rate
        FROM rpc_events
        WHERE {' AND '.join(where)}
        GROUP BY chain, env, rpc_arm
        ORDER BY n DESC, rpc_arm
        """
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        for r in rows:
            r["entity_type"] = "rpc_arm"
            r["entity_id"] = r.get("rpc_arm")
        return rows
