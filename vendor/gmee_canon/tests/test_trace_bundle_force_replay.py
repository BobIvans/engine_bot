import os
import uuid
from pathlib import Path

import pytest
import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import glue_select_params_from_cfg
from gmee.evidence import export_trace_evidence_bundle
from gmee.replay import replay_any_evidence_bundle


@pytest.mark.integration
def test_trace_scope_bundle_and_force_replay_roundtrip(runner, tmp_path: Path):
    # Admin runner (default DB) to create per-test databases
    admin = ClickHouseQueryRunner.from_env()
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    timeout_s = int(os.getenv("CLICKHOUSE_TIMEOUT_S", "30"))

    db_orig = f"gmee_orig_{uuid.uuid4().hex[:10]}"
    db_replay = f"gmee_replay_{uuid.uuid4().hex[:10]}"
    admin.execute_raw(f"CREATE DATABASE IF NOT EXISTS {db_orig}")
    admin.execute_raw(f"CREATE DATABASE IF NOT EXISTS {db_replay}")

    runner_orig = ClickHouseQueryRunner(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_orig,
        timeout_s=timeout_s,
        queries_registry_path="configs/queries.yaml",
    )
    runner_replay = ClickHouseQueryRunner(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_replay,
        timeout_s=timeout_s,
        queries_registry_path="configs/queries.yaml",
    )

    # Seed orig
    runner_orig.run_sql_file(Path("schemas/clickhouse.sql"))
    runner_orig.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    trade_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    trace_id = runner_orig.execute_raw(
        "SELECT trace_id FROM trades WHERE trade_id={trade_id:UUID} FORMAT TSV",
        params={"trade_id": str(trade_id)},
    ).strip()
    assert trace_id, "seed did not create trace_id for oracle trade"

    # Export trace bundle
    bundle_dir = tmp_path / "trace_bundle"
    export_trace_evidence_bundle(runner_orig, trace_id, bundle_dir)

    # Replay into clean DB
    runner_replay.run_sql_file(Path("schemas/clickhouse.sql"))
    replay_any_evidence_bundle(runner_replay, bundle_dir, verify_hashes=True)

    # Oracle assert
    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    params = glue_select_params_from_cfg(cfg, "solana")
    params = {**params, "chain": "solana", "trade_id": str(trade_id)}
    out = runner_replay.execute_function("glue_select", params).strip().splitlines()
    assert out and out[0].strip() == (
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\tU\t20\t250\t2025-01-01 01:00:21.750\t1"
    )

    # Replay again with --force (delete then insert) into same DB; should remain deterministic.
    replay_any_evidence_bundle(runner_replay, bundle_dir, force=True, verify_hashes=True)
    out2 = runner_replay.execute_function("glue_select", params).strip().splitlines()
    assert out2 and out2[0].strip() == out[0].strip()
