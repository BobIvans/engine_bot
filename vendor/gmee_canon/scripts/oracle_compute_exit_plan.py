#!/usr/bin/env python3
"""Manual oracle runner: seed dataset and print compute_exit_plan output.

Usage:
  python scripts/oracle_compute_exit_plan.py

Assumes ClickHouse is reachable at CLICKHOUSE_HOST/PORT (defaults localhost:8123).
"""
import uuid
from pathlib import Path

import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.planner import compute_exit_plan


def main() -> None:
    runner = ClickHouseQueryRunner.from_env()
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    trade_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    plan = compute_exit_plan("solana", trade_id, cfg, runner=runner)
    print(plan)

if __name__ == "__main__":
    main()
