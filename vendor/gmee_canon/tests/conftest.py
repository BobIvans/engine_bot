import os
import uuid
import pytest

from gmee.clickhouse import ClickHouseQueryRunner


@pytest.fixture(scope="function")
def ch_db_name() -> str:
    return f"gmee_test_{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="function")
def runner(ch_db_name: str):
    # Create isolated DB per test to avoid MergeTree duplicates affecting gates.
    base = ClickHouseQueryRunner.from_env()
    base.execute_raw(f"CREATE DATABASE IF NOT EXISTS {ch_db_name}")
    r = ClickHouseQueryRunner.from_env()
    r.database = ch_db_name
    # Keep env in sync for scripts that create their own runner from_env()
    old = os.environ.get("CLICKHOUSE_DATABASE")
    os.environ["CLICKHOUSE_DATABASE"] = ch_db_name
    try:
        yield r
    finally:
        try:
            base.execute_raw(f"DROP DATABASE IF EXISTS {ch_db_name} SYNC")
        except Exception:
            pass
        if old is None:
            os.environ.pop("CLICKHOUSE_DATABASE", None)
        else:
            os.environ["CLICKHOUSE_DATABASE"] = old
