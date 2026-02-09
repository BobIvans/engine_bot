"""Oracle gate for GMEE exit planner (P0).

This script is intended to be called from a main-repo CI runner.
It uses the canonical artifacts in this repo:
  - schemas/clickhouse.sql
  - scripts/seed_golden_dataset.sql
  - configs/golden_exit_engine.yaml
  - queries/04_glue_select.sql (via configs/queries.yaml registry)

It MUST fail (exit code != 0) on any drift.
"""

from __future__ import annotations

# Ensure repo root is importable when running as `python ci/<script>.py`
from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


import sys
import uuid
from pathlib import Path

import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import glue_select_params_from_cfg


EXPECTED_FILE = Path("ci/oracle_expected.tsv")
if not EXPECTED_FILE.exists():
    raise SystemExit("Missing ci/oracle_expected.tsv. Generate it via ci/generate_oracle_expected.py")
EXPECTED_TSV = EXPECTED_FILE.read_text(encoding="utf-8").strip()



def main() -> int:
    runner = ClickHouseQueryRunner.from_env()
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    trade_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    params = glue_select_params_from_cfg(cfg, "solana")
    params = {**params, "chain": "solana", "trade_id": str(trade_id)}

    out = runner.execute_function("glue_select", params).strip().splitlines()
    if not out:
        print("ERROR: glue_select returned no rows", file=sys.stderr)
        return 2
    got = out[0].strip()
    if got != EXPECTED_TSV:
        print("ERROR: oracle mismatch", file=sys.stderr)
        print(f"expected: {EXPECTED_TSV}", file=sys.stderr)
        print(f"got:      {got}", file=sys.stderr)
        return 3
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())