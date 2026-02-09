from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..base import GatherContext

@dataclass
class WalletProfile30DGatherer:
    """Reads canonical deterministic VIEW wallet_profile_30d (anchored on max(day))."""
    name: str = "wallet_profile_30d"
    limit: int = 5000

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM wallet_profile_30d
        WHERE chain = {chain:String}
        ORDER BY wallet
        LIMIT {limit:UInt32}
        """
        rows = ctx.ch.query_json(sql, params={"chain": ctx.chain, "limit": int(self.limit)}, database=ctx.database)
        # normalize field names: wallet_profile_30d uses column 'wallet'
        out: List[Dict[str, Any]] = []
        for r in rows:
            r2 = dict(r)
            r2.setdefault("entity_type", "wallet")
            r2.setdefault("entity_id", r.get("wallet"))
            r2.setdefault("chain", ctx.chain)
            out.append(r2)
        return out
