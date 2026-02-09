from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..base import GatherContext

@dataclass
class EntityKeyspaceGatherer:
    """NEW additional generic mechanism: define an entity keyspace over existing columns, and gather counts.

    This is a 'replicable template' to add new entity types (besides wallets) without schema changes:
    - entity_type: e.g. token_mint, pool_id, traced_wallet, rpc_arm, source
    - table: canonical table containing the column
    - column: the column name
    """
    entity_type: str
    table: str
    column: str
    name: str = "entity_keyspace"
    limit: int = 5000

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        if self.table not in {"signals_raw", "trade_attempts", "rpc_events", "trades"}:
            raise ValueError(f"EntityKeyspaceGatherer: unsupported table {self.table}")
        # base filters
        where = []
        params: Dict[str, Any] = {"chain": ctx.chain, "env": ctx.env, "limit": int(self.limit)}
        if "chain" in {"signals_raw", "trade_attempts", "rpc_events", "trades"}:
            where.append("chain = {chain:String}")
        if self.table in {"signals_raw", "trade_attempts", "rpc_events", "trades"}:
            where.append("env = {env:String}")
        # time window on best-effort timestamp columns
        if ctx.since_ts:
            ts_col = "signal_time" if self.table == "signals_raw" else "created_at" if self.table == "trade_attempts" else "sent_ts" if self.table == "rpc_events" else "buy_time"
            where.append(f"{ts_col} >= toDateTime64({{since:String}}, 3, 'UTC')")
            params["since"] = ctx.since_ts
        if ctx.until_ts:
            ts_col = "signal_time" if self.table == "signals_raw" else "created_at" if self.table == "trade_attempts" else "sent_ts" if self.table == "rpc_events" else "buy_time"
            where.append(f"{ts_col} < toDateTime64({{until:String}}, 3, 'UTC')")
            params["until"] = ctx.until_ts

        sql = f"""
        SELECT
          {self.column} AS entity_id,
          count() AS n
        FROM {self.table}
        WHERE {' AND '.join(where) if where else '1'}
          AND entity_id != ''
        GROUP BY entity_id
        ORDER BY n DESC
        LIMIT {{limit:UInt32}}
        """
        rows = ctx.ch.query_json(sql, params=params, database=ctx.database)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "entity_type": self.entity_type,
                "entity_id": r.get("entity_id"),
                "n": r.get("n"),
                "chain": ctx.chain,
                "env": ctx.env,
                "table": self.table,
                "column": self.column,
            })
        return out
