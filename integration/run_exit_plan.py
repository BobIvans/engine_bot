#!/usr/bin/env python3
"""integration/run_exit_plan.py

One-shot end-to-end demo (Iteration-1):

    strategy -> runtime cfg -> CANON SQL04 -> exit plan

What it does:
1) Connects to ClickHouse (HTTP)
2) Applies CANON DDL (vendor/gmee_canon/schemas/clickhouse.sql)
3) (Optional) seeds golden dataset (vendor/gmee_canon/scripts/seed_golden_dataset.sql)
4) Loads runtime engine cfg (integration/runtime/golden_exit_engine.yaml)
5) Builds SQL04 params (strict registry-driven names)
6) Executes CANON query queries/04_glue_select.sql (named params, no sed)
7) Writes a simple `forensics_events(kind='exit_plan')` row and prints the plan

Notes:
- vendor/gmee_canon is read-only CANON. This script lives in integration/.
- This demo uses the golden seeded trade_id by default, so results are reproducible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR = REPO_ROOT / "vendor" / "gmee_canon"

# Make vendored canon importable.
sys.path.insert(0, str(VENDOR))

from gmee.clickhouse import ClickHouseQueryRunner  # type: ignore
from gmee.config import glue_select_params_from_cfg  # type: ignore


class DemoError(RuntimeError):
    pass


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _split_sql_statements(sql: str) -> List[str]:
    """Very small splitter for DDL/seed scripts (no semicolons inside strings in CANON)."""
    out: List[str] = []
    buf: List[str] = []
    for line in sql.splitlines():
        buf.append(line)
        if line.strip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                out.append(stmt.rstrip(";"))
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail)
    return [s.strip() for s in out if s.strip()]


def apply_sql_file(runner: ClickHouseQueryRunner, path: Path) -> None:
    sql = _read_text(path)
    for stmt in _split_sql_statements(sql):
        runner.execute_raw(stmt)


def read_glue_select_registry_params(queries_yaml: Dict[str, Any]) -> List[str]:
    funcs = queries_yaml.get("functions")
    if not isinstance(funcs, dict):
        raise DemoError("configs/queries.yaml: missing 'functions'")
    glue = funcs.get("glue_select")
    if not isinstance(glue, dict):
        raise DemoError("configs/queries.yaml: missing 'functions.glue_select'")
    params = glue.get("params")
    if not isinstance(params, list) or not all(isinstance(x, str) for x in params):
        raise DemoError("configs/queries.yaml: 'functions.glue_select.params' must be list[str]")
    return params


def build_sql04_params_strict(*, engine_cfg: Dict[str, Any], queries_cfg: Dict[str, Any], chain: str, trade_id: str) -> Dict[str, Any]:
    """Build params for SQL04 (04_glue_select.sql) strictly matching registry names."""
    registry = read_glue_select_registry_params(queries_cfg)

    # Engine-derived params (no chain/trade_id in engine_cfg)
    core = glue_select_params_from_cfg(engine_cfg, chain=chain)
    params = {"chain": chain, "trade_id": trade_id, **core}

    missing = sorted(set(registry) - set(params))
    extra = sorted(set(params) - set(registry))
    if missing or extra:
        raise DemoError(f"SQL04 params mismatch vs registry. missing={missing} extra={extra}")

    # Stable order (use registry order)
    return {k: params[k] for k in registry}


def parse_sql04_tsv(tsv: str) -> Tuple[str, str, int, int, str, int]:
    """Expected SQL04 output (CANON v23):
    trade_id, mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag
    """
    lines = [ln for ln in tsv.splitlines() if ln.strip()]
    if not lines:
        raise DemoError("SQL04 returned empty output")

    parts = lines[0].split("\t")
    if len(parts) != 6:
        raise DemoError(f"Expected 6 TSV columns from SQL04, got {len(parts)}: {parts}")

    trade_id = parts[0]
    mode = parts[1]
    planned_hold_sec = int(parts[2])
    epsilon_ms = int(parts[3])
    planned_exit_ts = parts[4]  # keep as string (DateTime64)
    aggr_flag = int(parts[5])
    return trade_id, mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag


def write_exit_plan_event(
    runner: ClickHouseQueryRunner,
    *,
    chain: str,
    env: str,
    trade_id: str,
    mode: str,
    planned_hold_sec: int,
    epsilon_ms: int,
    planned_exit_ts: str,
    aggr_flag: int,
) -> None:
    details = {
        "trade_id": trade_id,
        "mode": mode,
        "planned_hold_sec": planned_hold_sec,
        "epsilon_ms": epsilon_ms,
        "planned_exit_ts": planned_exit_ts,
        "aggr_flag": aggr_flag,
        "ts_utc": _utc_now().isoformat(),
    }

    runner.execute_raw(
        """
        INSERT INTO forensics_events (
            event_id,
            chain,
            env,
            ts,
            kind,
            severity,
            details_json
        ) VALUES (
            {event_id:UUID},
            {chain:String},
            {env:String},
            {ts:DateTime64(3)},
            {kind:String},
            {severity:String},
            {details_json:String}
        )
        """,
        params={
            "event_id": str(uuid.uuid4()),
            "chain": chain,
            "env": env,
            "ts": _utc_now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "kind": "exit_plan",
            "severity": "info",
            "details_json": json.dumps(details, separators=(",", ":"), ensure_ascii=False),
        },
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch-url", default=os.getenv("CLICKHOUSE_URL", "http://localhost:8123"))
    ap.add_argument("--ch-user", default=os.getenv("CLICKHOUSE_USER", "default"))
    ap.add_argument("--ch-password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))

    ap.add_argument("--env", default=os.getenv("GMEE_ENV", "canary"))
    ap.add_argument("--chain", default=os.getenv("GMEE_CHAIN", "solana"))

    ap.add_argument(
        "--trade-id",
        default="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        help="Default is the trade_id used by CANON seed_golden_dataset.sql",
    )
    ap.add_argument(
        "--seed-golden",
        dest="seed_golden",
        action="store_true",
        help="Seed CANON golden dataset (scripts/seed_golden_dataset.sql)",
    )
    # Back-compat alias (kept for older docs / scripts)
    ap.add_argument("--seed", dest="seed_golden", action="store_true", help=argparse.SUPPRESS)

    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not connect to ClickHouse; just build and print SQL04 params.",
    )

    ap.add_argument(
        "--canon-root",
        default=str(VENDOR),
        help="Path to vendor/gmee_canon (read-only)",
    )
    ap.add_argument(
        "--runtime-engine-cfg",
        default=str(REPO_ROOT / "integration" / "runtime" / "golden_exit_engine.yaml"),
        help="Generated runtime engine cfg in CANON schema",
    )

    args = ap.parse_args()

    canon_root = Path(args.canon_root)
    ddl_path = canon_root / "schemas" / "clickhouse.sql"
    seed_path = canon_root / "scripts" / "seed_golden_dataset.sql"
    queries_yaml_path = canon_root / "configs" / "queries.yaml"
    sql04_path = canon_root / "queries" / "04_glue_select.sql"

    for p in (ddl_path, queries_yaml_path, sql04_path):
        if not p.exists():
            raise DemoError(f"Missing CANON file: {p}")

    runtime_cfg_path = Path(args.runtime_engine_cfg)
    if not runtime_cfg_path.exists():
        raise DemoError(
            f"Missing runtime engine cfg: {runtime_cfg_path}\n"
            f"Run: python integration/config_mapper.py --out {runtime_cfg_path}"
        )

    # Build params strictly vs registry (this works even without ClickHouse)
    engine_cfg = _load_yaml(runtime_cfg_path)
    queries_cfg = _load_yaml(queries_yaml_path)

    params = build_sql04_params_strict(
        engine_cfg=engine_cfg,
        queries_cfg=queries_cfg,
        chain=args.chain,
        trade_id=args.trade_id,
    )

    if args.dry_run:
        print(json.dumps({"sql04_params": params}, indent=2, ensure_ascii=False))
        return

    runner = ClickHouseQueryRunner(base_url=args.ch_url, user=args.ch_user, password=args.ch_password)

    # 1) DDL
    apply_sql_file(runner, ddl_path)

    # 2) Seed (optional, but recommended for demo)
    if args.seed_golden:
        if not seed_path.exists():
            raise DemoError(f"Missing seed script: {seed_path}")
        apply_sql_file(runner, seed_path)

    # 3) Execute SQL04
    sql04 = _read_text(sql04_path)
    tsv = runner.execute_tsv(sql04, params)

    trade_id, mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag = parse_sql04_tsv(tsv)

    # 4) Write-back (simple event)
    write_exit_plan_event(
        runner,
        chain=args.chain,
        env=args.env,
        trade_id=trade_id,
        mode=mode,
        planned_hold_sec=planned_hold_sec,
        epsilon_ms=epsilon_ms,
        planned_exit_ts=planned_exit_ts,
        aggr_flag=aggr_flag,
    )

    print("OK exit plan")
    print(
        json.dumps(
            {
                "trade_id": trade_id,
                "mode": mode,
                "planned_hold_sec": planned_hold_sec,
                "epsilon_ms": epsilon_ms,
                "planned_exit_ts": planned_exit_ts,
                "aggr_flag": aggr_flag,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
