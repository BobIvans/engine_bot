import os
import uuid
import yaml
from pathlib import Path

import pytest

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.planner import compute_exit_plan


@pytest.mark.integration
def test_oracle_compute_exit_plan_matches_expected_tsv(runner):
    # This test assumes ClickHouse is reachable (e.g., via docker-compose or CI service).

    # Apply schema + seed deterministic dataset
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))

    trade_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    plan = compute_exit_plan("solana", trade_id, cfg, runner=runner)

    # Must match the repo's canonical oracle expected output used by CI (TSV).
    assert plan.mode == "U"
    assert plan.planned_hold_sec == 20
    assert plan.epsilon_ms == 250
    assert plan.planned_exit_ts == "2025-01-01 01:00:21.750"
    assert plan.aggr_flag == 1
