from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from uuid import UUID

import yaml

from .clickhouse import ClickHouseQueryRunner
from .config import REPO_ROOT


@dataclass(frozen=True)
class DiscoveryResult:
    trade_id: Optional[UUID]
    trace_id: UUID
    chain: str
    env: str
    source: str
    traced_wallet: Optional[str]
    token_mint: Optional[str]
    pool_id: Optional[str]
    buy_time: Optional[str]
    signal_time: Optional[str]


def _load_dimensions(path: str | Path = "configs/discovery_dimensions.yaml") -> Mapping[str, Any]:
    p = (REPO_ROOT / path).resolve()
    if not p.exists():
        return {"base_filters": {}}
    return yaml.safe_load(p.read_text()) or {"base_filters": {}}


def _parse_where_pairs(where: Iterable[str]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    Supports:
      - base filters: key=value
      - payload.<k>=v  (signals_raw.payload_json)
      - details.<k>=v  (forensics_events.details_json)
    """
    base: Dict[str, str] = {}
    payload: Dict[str, str] = {}
    details: Dict[str, str] = {}
    for w in where:
        if "=" not in w:
            continue
        k, v = w.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k.startswith("payload."):
            payload[k[len("payload."):]] = v
        elif k.startswith("details."):
            details[k[len("details."):]] = v
        else:
            base[k] = v
    return base, payload, details


def discover_trades(
    runner: ClickHouseQueryRunner,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    where: Optional[List[str]] = None,
    limit: int = 200,
) -> List[DiscoveryResult]:
    """
    Generic discovery for new data variables:
      - base filters via configs/discovery_dimensions.yaml
      - payload.* filters via JSONExtractString(payload_json, key)
      - details.* filters via JSONExtractString(details_json, key) (forensics)
    """
    dims = _load_dimensions()
    base_filters = dims.get("base_filters", {})

    base, payload, details = _parse_where_pairs(where or [])

    # We use trades as primary (best join point). If filters refer to signals_raw only, we still can join by trace_id.
    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": int(limit)}

    if since:
        clauses.append("t.buy_time >= {since:DateTime64(3)}")
        params["since"] = since
    if until:
        clauses.append("t.buy_time <= {until:DateTime64(3)}")
        params["until"] = until

    # base filters
    for k, v in base.items():
        if k not in base_filters:
            raise ValueError(f"Unknown base filter '{k}'. Add it to configs/discovery_dimensions.yaml or use payload./details. syntax.")
        spec = base_filters[k]
        table = spec["table"]
        col = spec["column"]
        typ = spec["type"]
        pname = f"f_{k}"
        if table == "trades":
            clauses.append(f"t.{col} = {{{pname}:{typ}}}")
        elif table == "signals_raw":
            clauses.append(f"s.{col} = {{{pname}:{typ}}}")
        else:
            raise ValueError(f"Unsupported table in discovery mapping: {table}")
        params[pname] = v

    # payload filters on signals_raw.payload_json
    for k, v in payload.items():
        pname = f"p_{k.replace('.','_')}"
        clauses.append(f"JSONExtractString(s.payload_json, {{k_{pname}:String}}) = {{{pname}:String}}")
        params[pname] = v
        params[f"k_{pname}"] = k

    # details filters on forensics_events.details_json (join by trace_id)
    details_join = ""
    for k, v in details.items():
        pname = f"d_{k.replace('.','_')}"
        details_join = "LEFT JOIN forensics_events f ON f.trace_id = t.trace_id"
        clauses.append(f"JSONExtractString(f.details_json, {{k_{pname}:String}}) = {{{pname}:String}}")
        params[pname] = v
        params[f"k_{pname}"] = k

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
      t.trade_id, t.trace_id, t.chain, t.env, t.source,
      t.traced_wallet, t.token_mint, t.pool_id,
      toString(t.buy_time) AS buy_time,
      toString(t.signal_time) AS signal_time
    FROM trades t
    LEFT JOIN signals_raw s ON s.trace_id = t.trace_id
    {details_join}
    {where_sql}
    ORDER BY t.buy_time ASC, t.trade_id ASC
    LIMIT {{limit:UInt32}}
    FORMAT JSONEachRow
    """

    rows = runner.select_json_each_row_typed(sql, params)
    out: List[DiscoveryResult] = []
    for r in rows:
        out.append(
            DiscoveryResult(
                trade_id=UUID(r["trade_id"]) if r.get("trade_id") else None,
                trace_id=UUID(r["trace_id"]),
                chain=r.get("chain") or "",
                env=r.get("env") or "",
                source=r.get("source") or "",
                traced_wallet=r.get("traced_wallet"),
                token_mint=r.get("token_mint"),
                pool_id=r.get("pool_id"),
                buy_time=r.get("buy_time"),
                signal_time=r.get("signal_time"),
            )
        )
    return out


def discover_trace_from_trade(runner: ClickHouseQueryRunner, trade_id: UUID) -> Optional[UUID]:
    sql = "SELECT trace_id FROM trades WHERE trade_id = {trade_id:UUID} LIMIT 1 FORMAT JSONEachRow"
    rows = runner.select_json_each_row_typed(sql, {"trade_id": str(trade_id)})
    if not rows:
        return None
    return UUID(rows[0]["trace_id"])
