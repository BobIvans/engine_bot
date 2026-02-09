import tempfile
from pathlib import Path

import pytest

from gmee.bundle_validate import validate_bundle
from gmee.evidence import export_trade_evidence_bundle


@pytest.mark.integration
def test_exported_trade_bundle_validates(runner):
    runner.run_sql_file("schemas/clickhouse.sql")
    runner.run_sql_file("scripts/seed_golden_dataset.sql")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "bundle"
        export_trade_evidence_bundle(
            runner,
            trade_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            out_dir=out,
        )
        problems = validate_bundle(out)
        assert not problems, f"bundle validation failed: {problems}"
