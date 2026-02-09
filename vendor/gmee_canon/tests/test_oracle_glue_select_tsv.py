import uuid
from pathlib import Path

import pytest
import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import glue_select_params_from_cfg


@pytest.mark.integration
def test_oracle_glue_select_returns_expected_tsv_line(runner):
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))

    trade_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    params = glue_select_params_from_cfg(cfg, "solana")
    params = {**params, "chain": "solana", "trade_id": str(trade_id)}

    out = runner.execute_function("glue_select", params).strip().splitlines()
    assert out, "glue_select returned no rows"
    assert out[0].strip() == (
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\tU\t20\t250\t2025-01-01 01:00:21.750\t1"
    )
