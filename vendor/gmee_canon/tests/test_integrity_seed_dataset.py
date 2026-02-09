import pytest

from gmee.integrity import check_integrity


@pytest.mark.integration
def test_integrity_checks_pass_on_seed_golden_dataset(runner):
    runner.run_sql_file("schemas/clickhouse.sql")
    runner.run_sql_file("scripts/seed_golden_dataset.sql")

    rep = check_integrity(runner, trade_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    rep.assert_ok()
