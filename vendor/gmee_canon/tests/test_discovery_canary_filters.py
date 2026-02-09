from __future__ import annotations

import os
from pathlib import Path

import pytest

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.discovery import discover_trades


@pytest.mark.integration
def test_discovery_filters_on_canary_seed(tmp_path: Path) -> None:
    """
    P0-safe discovery smoke:
    - apply schema
    - seed canary
    - discover by base filter (traced_wallet) and by payload filter (payload.kind)
    """
    runner = ClickHouseQueryRunner.from_env()

    runner.run_sql_file("schemas/clickhouse.sql")
    runner.run_sql_file("scripts/canary_golden_trace.sql")

    # base filter
    res1 = discover_trades(runner, where=["traced_wallet=wallet_X"], limit=10)
    assert len(res1) >= 1

    # generic new-variable filter: payload.kind=synthetic (from signals_raw.payload_json)
    res2 = discover_trades(runner, where=["payload.kind=synthetic"], limit=10)
    assert len(res2) >= 1

    # combined
    res3 = discover_trades(runner, where=["traced_wallet=wallet_X", "payload.kind=synthetic"], limit=10)
    assert len(res3) >= 1
