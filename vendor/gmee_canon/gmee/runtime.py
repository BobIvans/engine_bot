from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

from typing import Any, Mapping, Optional

from .clickhouse import ClickHouseQueryRunner, extract_placeholders
from .config import compute_config_hash, load_engine_config


def assert_registry_parity(queries_registry_path: str | Path = "configs/queries.yaml") -> None:
    """Fail fast if configs/queries.yaml params drift from SQL placeholders (P0)."""
    runner = ClickHouseQueryRunner.from_env(queries_registry_path=str(queries_registry_path))
    for name in runner.list_functions():
        qd = runner.get_query_def(name)
        sql = runner.read_sql(qd.sql_path)
        placeholders = set(extract_placeholders(sql).keys())
        reg = set(qd.params)
        if placeholders != reg:
            raise RuntimeError(
                f"Registry↔SQL drift for {name}: registry={sorted(reg)} sql={sorted(placeholders)}"
            )


def assert_wallet_profile_view_deterministic(clickhouse_sql_path: str | Path = "schemas/clickhouse.sql") -> None:
    """Heuristic guard: wallet_profile_30d should not be anchored on now()/today() (P0)."""
    p = Path(clickhouse_sql_path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    ddl = p.read_text(encoding="utf-8")
    # Grab view definition block (best-effort)
    m = re.search(r"CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\s+wallet_profile_30d.*?;", ddl, flags=re.S | re.I)
    if not m:
        return
    view_sql = m.group(0).lower()
    if "now(" in view_sql or "today(" in view_sql:
        raise RuntimeError("wallet_profile_30d appears time-anchored on now()/today(); must be deterministic (P0)")


def assert_config_hash(engine_cfg: Mapping[str, Any], config_hash: str) -> None:
    want = compute_config_hash(engine_cfg)
    if (config_hash or "").strip().lower() != want.lower():
        raise RuntimeError(f"config_hash mismatch: ctx={config_hash} computed={want}")


def assert_runtime_contracts(
    *,
    engine_cfg_path: str | Path = "configs/golden_exit_engine.yaml",
    queries_registry_path: str | Path = "configs/queries.yaml",
    clickhouse_sql_path: str | Path = "schemas/clickhouse.sql",
    config_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Run lightweight P0 contract assertions at app startup (no DB required)."""
    engine_cfg = load_engine_config(engine_cfg_path)
    assert_registry_parity(queries_registry_path)
    assert_wallet_profile_view_deterministic(clickhouse_sql_path)
    if config_hash is not None:
        assert_config_hash(engine_cfg, config_hash)
    return engine_cfg
