from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..base import DataGatherer, GatherContext
from ...capture.uv_store import UniversalVarStore


def _load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def _best_id(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


@dataclass
class ExternalUVJoinGatherer(DataGatherer):
    """Join Universal Variables (filesystem artifacts) onto trades.

    Intended for trial/demo windows: you capture provider data, normalize into UV, then
    correlate with trade outcomes *without changing ClickHouse schema*.

    Outputs per-trade feature rows keyed by trade_id.
    """

    name: str
    params: Dict[str, Any]

    def gather(self, ctx: GatherContext) -> List[Dict[str, Any]]:
        uv_root = Path(self.params.get('uv_root', 'out/capture'))
        snapshot_id = self.params.get('snapshot_id')
        if not snapshot_id:
            raise ValueError('external_uv_join requires params.snapshot_id (points to out/capture/uv/<provider>/<snapshot_id>/uv.jsonl)')

        providers = self.params.get('providers') or []
        if not providers:
            # If not specified, load all providers found under uv_root/uv/*/<snapshot_id>/uv.jsonl
            uv_dir = uv_root / 'uv'
            if uv_dir.exists():
                providers = [p.name for p in uv_dir.iterdir() if p.is_dir()]

        feature_cfg_path = Path(self.params.get('feature_cfg', 'configs/providers/external_uv_feature_join.yaml'))
        if not feature_cfg_path.is_absolute():
            feature_cfg_path = ctx_repo_root() / feature_cfg_path
        feature_cfg = _load_yaml(feature_cfg_path)
        entity_features = feature_cfg.get('entity_features', {})

        uv_paths: List[Path] = []
        for provider_id in providers:
            p = uv_root / 'uv' / str(provider_id) / str(snapshot_id) / 'uv.jsonl'
            if p.exists():
                uv_paths.append(p)

        store = UniversalVarStore.load(uv_paths)

        since = ctx.since_ts or '1970-01-01 00:00:00.000'
        until = ctx.until_ts or '2100-01-01 00:00:00.000'

        trade_rows = ctx.ch.query_json(
            """
            SELECT
              trade_id,
              trace_id,
              chain,
              env,
              buy_time,
              traced_wallet,
              token_mint,
              pool_id,
              dex_route,
              entry_confirm_quality,
              exit_confirm_quality,
              success_bool,
              roi,
              slippage_pct,
              entry_latency_ms
            FROM trades
            WHERE chain = {chain:String}
              AND env = {env:String}
              AND buy_time >= {since:DateTime64(3)}
              AND buy_time < {until:DateTime64(3)}
            """,
            params={
                'chain': ctx.chain,
                'env': ctx.env,
                'since': since,
                'until': until,
            },
        )

        out: List[Dict[str, Any]] = []
        for tr in trade_rows:
            row: Dict[str, Any] = {
                'trade_id': tr.get('trade_id'),
                'trace_id': tr.get('trace_id'),
                'chain': tr.get('chain'),
                'env': tr.get('env'),
                'buy_time': tr.get('buy_time'),
            }

            buy_ts = str(tr.get('buy_time'))

            # Iterate configured entity types and variables
            for entity_type, cfg in entity_features.items():
                id_field = cfg.get('id_field')
                if not id_field:
                    continue
                ent_id = _best_id(tr.get(id_field))
                if not ent_id:
                    continue

                for var_name in (cfg.get('vars') or []):
                    uv = store.last_before(entity_type, ent_id, var_name, buy_ts)
                    if not uv:
                        continue
                    k = f"uv__{entity_type}__{var_name}"
                    row[k] = uv.value
                    row[k + '__unit'] = uv.unit
                    row[k + '__confidence'] = uv.confidence
                    row[k + '__provider'] = uv.source_provider
                    row[k + '__snapshot'] = uv.snapshot_id

            out.append(row)

        return out


def ctx_repo_root() -> Path:
    # Late import to avoid circulars.
    from ...util import repo_root

    return repo_root()
