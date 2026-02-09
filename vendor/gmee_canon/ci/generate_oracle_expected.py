#!/usr/bin/env python3
"""Generate ci/oracle_expected.tsv from canonical inputs (P0).

P0 intent:
- expected TSV is an artifact (file), not an inline string in CI/workflows.
- generation is deterministic given:
    - schemas/clickhouse.sql
    - scripts/seed_golden_dataset.sql
    - configs/golden_exit_engine.yaml
    - queries/04_glue_select.sql + configs/queries.yaml registry

NOTE: In P0, canonical seed/YAML must not change, so the expected file should be stable.
"""

from __future__ import annotations

# Ensure repo root is importable when running as `python ci/<script>.py`
from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


import argparse
from pathlib import Path

import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.config import glue_select_params_from_cfg


DEFAULT_TRADE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEFAULT_CHAIN = "solana"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ci/oracle_expected.tsv", help="Output TSV path")
    ap.add_argument("--trade-id", default=DEFAULT_TRADE_ID)
    ap.add_argument("--chain", default=DEFAULT_CHAIN)
    args = ap.parse_args()

    out_path = Path(args.out)

    runner = ClickHouseQueryRunner.from_env()

    # Apply schema + seed (idempotent)
    runner.run_sql_file(Path("schemas/clickhouse.sql"))
    runner.run_sql_file(Path("scripts/seed_golden_dataset.sql"))

    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    params = glue_select_params_from_cfg(cfg, args.chain)
    params = {**params, "chain": args.chain, "trade_id": args.trade_id}

    got = runner.execute_function("glue_select", params).strip().splitlines()
    if not got:
        raise SystemExit("glue_select returned no rows")

    line = got[0].strip()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(line + "\n", encoding="utf-8")
    print(f"Wrote {out_path}: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())