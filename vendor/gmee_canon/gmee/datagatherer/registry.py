from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

from .base import DataGatherer, GatherContext
from .gatherers.wallet_profile import WalletProfile30DGatherer
from .gatherers.rpc_arm import RpcArmStatsGatherer
from .gatherers.token_pool import TokenPoolRegimeGatherer
from .gatherers.signal_source import SignalSourceStatsGatherer
from .gatherers.json_key_stats import JsonKeyStatsGatherer
from .gatherers.entity_keyspace import EntityKeyspaceGatherer
from .gatherers.numeric_quantiles import NumericQuantilesGatherer
from .gatherers.categorical_distribution import CategoricalDistributionGatherer
from .gatherers.volatility import VolatilityRegimeGatherer
from .gatherers.window_delta import WindowDeltaGatherer
from .gatherers.cooccurrence import CooccurrenceGatherer
from .gatherers.signal_quality import SignalQualityGatherer
from .gatherers.external_uv_join import ExternalUVJoinGatherer

_TYPE_MAP = {
    "wallet_profile_30d": WalletProfile30DGatherer,
    "rpc_arm_stats": RpcArmStatsGatherer,
    "token_pool_regime": TokenPoolRegimeGatherer,
    "signal_source_stats": SignalSourceStatsGatherer,
    "json_key_stats": JsonKeyStatsGatherer,
    "entity_keyspace": EntityKeyspaceGatherer,
"numeric_quantiles": NumericQuantilesGatherer,
"categorical_distribution": CategoricalDistributionGatherer,
"volatility_regime": VolatilityRegimeGatherer,
"signal_quality": SignalQualityGatherer,
    # Non-canonical: join filesystem Universal Variables onto trades for trial windows
    "external_uv_join": ExternalUVJoinGatherer,
}

@dataclass
class DataGathererRegistry:
    gatherers: List[DataGatherer]

    @staticmethod
    def load(path: str) -> "DataGathererRegistry":
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        items = cfg.get("gatherers", [])
        out: List[DataGatherer] = []
        for item in items:
            gtype = item.get("type")
            params = item.get("params", {}) or {}
            cls = _TYPE_MAP.get(gtype)
            if not cls:
                raise ValueError(f"Unknown gatherer type: {gtype}")
            out.append(cls(**params))
        return DataGathererRegistry(gatherers=out)

    def run_all(self, ctx: GatherContext) -> Dict[str, List[Dict[str, Any]]]:
        results: Dict[str, List[Dict[str, Any]]] = {}
        for g in self.gatherers:
            name = getattr(g, "name", g.__class__.__name__)
            results[name] = g.gather(ctx)
        return results
