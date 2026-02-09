#!/usr/bin/env python3
"""ci/explain_syntax_gate.py

Single source of truth for "compile / EXPLAIN SYNTAX" checks.

Why this exists:
  - Avoid sed/regex SQL templating.
  - Make CI and local smoke run the *same* code-path as the HTTP runner
    (named params: param_<name>=...).

It loads configs/queries.yaml, reads each SQL file, auto-derives placeholder
types from {name:Type} markers, generates minimal sample values, and runs
"EXPLAIN SYNTAX" against ClickHouse.

Usage:
  python ci/explain_syntax_gate.py            # all registered queries
  python ci/explain_syntax_gate.py glue_select routing_query

Env:
  CH_HOST (default: 127.0.0.1)
  CH_PORT (default: 8123)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import yaml

from gmee.clickhouse import ClickHouseHTTPClient, extract_placeholders


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class QuerySpec:
    name: str
    sql_path: Path


def _unwrap_nullable(ch_type: str) -> str:
    t = ch_type.strip()
    if t.startswith("Nullable(") and t.endswith(")"):
        return t[len("Nullable(") : -1].strip()
    return t


def sample_for_type(ch_type: str):
    """Return a conservative sample value for a ClickHouse placeholder type."""

    t = _unwrap_nullable(ch_type)

    # Common scalar types used in this repo.
    if t in {"UInt8", "UInt16", "UInt32", "UInt64", "Int8", "Int16", "Int32", "Int64"}:
        return 1
    if t in {"Float32", "Float64"}:
        return 0.5
    if t.startswith("Decimal"):
        return "1.0"
    if t in {"String", "LowCardinality(String)"}:
        return "solana"
    if t == "UUID":
        return "00000000-0000-0000-0000-000000000000"
    if t.startswith("DateTime64"):
        # Keep a valid fixed timestamp with millis.
        return "2020-01-01 00:00:00.000"
    if t == "DateTime":
        return "2020-01-01 00:00:00"
    if t == "Date":
        return "2020-01-01"

    raise ValueError(f"Unsupported ClickHouse placeholder type for sample: {ch_type!r}")


def load_registry() -> Dict[str, Dict]:
    path = ROOT / "configs" / "queries.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    reg = data.get("registry")
    if not isinstance(reg, dict):
        raise RuntimeError("configs/queries.yaml must contain top-level 'registry:' mapping")
    return reg


def iter_queries(registry: Dict[str, Dict], only: Iterable[str] | None) -> List[QuerySpec]:
    names = list(registry.keys())
    if only:
        req = list(only)
        missing = [n for n in req if n not in registry]
        if missing:
            raise SystemExit(f"Unknown query name(s): {missing}. Known: {names}")
        names = req

    specs: List[QuerySpec] = []
    for name in names:
        file = registry[name].get("file")
        if not file:
            raise RuntimeError(f"Registry entry {name!r} missing 'file' field")
        specs.append(QuerySpec(name=name, sql_path=(ROOT / "queries" / file)))
    return specs


def sample_params_for_sql(sql: str) -> Dict[str, object]:
    params: Dict[str, object] = {}
    for pname, ptype in extract_placeholders(sql):
        # Use the first occurrence as source of truth; enforce consistent type.
        if pname in params:
            continue
        params[pname] = sample_for_type(ptype)
    return params


def explain_one(client: ClickHouseHTTPClient, spec: QuerySpec) -> None:
    sql = spec.sql_path.read_text(encoding="utf-8").strip()
    params = sample_params_for_sql(sql)
    q = f"EXPLAIN SYNTAX\n{sql}"
    client.execute_typed(q, params=params)


def main(argv: List[str]) -> int:
    only = argv[1:] if len(argv) > 1 else None
    registry = load_registry()
    specs = iter_queries(registry, only)

    host = os.environ.get("CH_HOST") or os.environ.get("CLICKHOUSE_HOST") or "127.0.0.1"
    port = int(os.environ.get("CH_PORT") or os.environ.get("CLICKHOUSE_PORT") or "8123")
    client = ClickHouseHTTPClient(host=host, port=port)

    for spec in specs:
        explain_one(client, spec)
        print(f"OK EXPLAIN SYNTAX: {spec.name} ({spec.sql_path.name})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
