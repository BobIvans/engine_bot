from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import glue_select_params_from_cfg
from gmee.evidence import export_trade_evidence_bundle
from gmee.replay import replay_trade_evidence_bundle

ORACLE_TRADE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
EXPECTED_LINE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\tU\t20\t250\t2025-01-01 01:00:21.750\t1"


def _mk_runner(database: str) -> ClickHouseQueryRunner:
    base = ClickHouseQueryRunner.from_env()
    return ClickHouseQueryRunner(
        host=base.host,
        port=base.port,
        user=base.user,
        password=base.password,
        database=database,
        timeout_s=base.timeout_s,
        queries_registry_path=base._registry_path,
    )


@pytest.mark.integration
def test_evidence_bundle_roundtrip_glue_select(tmp_path: Path) -> None:
    base = ClickHouseQueryRunner.from_env()

    orig_db = f"gmee_p0_orig_{uuid.uuid4().hex[:8]}"
    repl_db = f"gmee_p0_repl_{uuid.uuid4().hex[:8]}"

    # Create databases under default DB context
    base.execute_raw(f"CREATE DATABASE IF NOT EXISTS {orig_db}")
    base.execute_raw(f"CREATE DATABASE IF NOT EXISTS {repl_db}")

    try:
        orig = _mk_runner(orig_db)
        repl = _mk_runner(repl_db)

        # Setup original + seed oracle dataset
        orig.run_sql_file("schemas/clickhouse.sql")
        orig.run_sql_file("scripts/seed_golden_dataset.sql")

        # Export evidence bundle for oracle trade
        bundle_dir = tmp_path / "bundle"
        export_trade_evidence_bundle(orig, ORACLE_TRADE_ID, bundle_dir)

        # Setup replay DB and replay
        repl.run_sql_file("schemas/clickhouse.sql")
        replay_trade_evidence_bundle(repl, bundle_dir)

        # Run glue_select in replay DB and compare to expected TSV line
        cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
        params = glue_select_params_from_cfg(cfg, "solana")
        params = {**params, "chain": "solana", "trade_id": ORACLE_TRADE_ID}

        out = repl.execute_function("glue_select", params).strip().splitlines()[0].strip()
        assert out == EXPECTED_LINE

        # Basic row-count parity for this trade_id
        for table in ["trade_attempts", "rpc_events", "trades", "microticks_1s"]:
            q = f"SELECT count() FROM {table} WHERE trade_id={{trade_id:UUID}}"
            c1 = orig.select_int_typed(q, {"trade_id": ORACLE_TRADE_ID})
            c2 = repl.select_int_typed(q, {"trade_id": ORACLE_TRADE_ID})
            assert c1 == c2, f"row-count drift in {table}: orig={c1} repl={c2}"

    finally:
        # Cleanup
        base.execute_raw(f"DROP DATABASE IF EXISTS {orig_db}")
        base.execute_raw(f"DROP DATABASE IF EXISTS {repl_db}")
