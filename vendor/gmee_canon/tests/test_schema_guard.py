import pytest

from gmee.schema_guard import assert_p0_schema


@pytest.mark.integration
def test_schema_guard_passes_on_fresh_schema(runner):
    runner.run_sql_file("schemas/clickhouse.sql")
    assert_p0_schema(runner)
