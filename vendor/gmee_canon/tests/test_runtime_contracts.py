from __future__ import annotations

from gmee.runtime import assert_runtime_contracts


def test_runtime_contracts_pass_on_repo_canon(runner):
    # Should not require ClickHouse running; validates local canon files.
    assert_runtime_contracts(
        engine_cfg_path="configs/golden_exit_engine.yaml",
        queries_registry_path="configs/queries.yaml",
        clickhouse_sql_path="schemas/clickhouse.sql",
    )
