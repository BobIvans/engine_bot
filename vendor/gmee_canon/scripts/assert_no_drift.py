#!/usr/bin/env python3
"""scripts/assert_no_drift.py — P0 anti-drift gate (Variant A)

This script exists so agents/Codex can write business-code **without guessing**.
It must catch drift between YAML ↔ SQL ↔ DDL ↔ docs.

Asserts:
- configs/queries.yaml params match SQL placeholders in queries/*.sql (1:1, no extras)
- configs/golden_exit_engine.yaml required keys exist
- queries/04_glue_select.sql has required placeholders and contains NO hardcoded
  numeric literals equal to YAML thresholds (Variant A)
- base quantile mapping contract is present in SQL and matches YAML
- schemas/clickhouse.sql TTLs match configs/golden_exit_engine.yaml retention
- docs/CONTRACT_MATRIX.md mentions YAML sources and anti-drift rules
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG_ENGINE = ROOT / "configs" / "golden_exit_engine.yaml"
CFG_QUERIES = ROOT / "configs" / "queries.yaml"
GLUE_SQL = ROOT / "queries" / "04_glue_select.sql"
CONTRACT_MATRIX = ROOT / "docs" / "CONTRACT_MATRIX.md"
CH_DDL = ROOT / "schemas" / "clickhouse.sql"

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+):([^}]+)\}")


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def load_yaml(p: Path) -> dict:
    return yaml.safe_load(read_text(p))


def extract_placeholders(sql: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER_RE.finditer(sql)}


def strip_sql_comments(sql: str) -> str:
    # Remove /* ... */ and -- ... comments (best-effort; good enough for P0 gates)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    return sql


def ddl_block(ddl: str, table: str) -> str:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}\b.*?;", ddl, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        fail(f"schemas/clickhouse.sql: missing CREATE TABLE for '{table}'")
    return m.group(0)


def ttl_days(block: str) -> int | None:
    m = re.search(r"\bTTL\b[^;]*?\bINTERVAL\s+(\d+)\s+DAY\b", block, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def main() -> None:
    for p in (CFG_ENGINE, CFG_QUERIES, GLUE_SQL, CONTRACT_MATRIX, CH_DDL):
        if not p.exists():
            fail(f"Missing {p}")

    engine = load_yaml(CFG_ENGINE)
    queries = load_yaml(CFG_QUERIES)
    glue_sql_raw = read_text(GLUE_SQL)
    glue_sql = strip_sql_comments(glue_sql_raw)

    # 0) Determinism: oracle glue SQL must not depend on wall-clock
    if re.search(r"\bnow\w*\s*\(", glue_sql, flags=re.IGNORECASE):
        fail("queries/04_glue_select.sql must not use now()/now64()/today() — make it deterministic")
    if re.search(r"\brand\w*\s*\(", glue_sql, flags=re.IGNORECASE):
        fail("queries/04_glue_select.sql must not use rand() — make it deterministic")

    # 1) configs/queries.yaml params match SQL placeholders (strict 1:1)
    funcs = queries.get("functions", {})
    if "glue_select" not in funcs:
        fail("configs/queries.yaml: missing functions.glue_select")

    for fn_name, fn in funcs.items():
        sql_path = ROOT / fn["sql"]
        if not sql_path.exists():
            fail(f"configs/queries.yaml: {fn_name} sql path not found: {sql_path}")
        sql_text = read_text(sql_path)
        ph = extract_placeholders(sql_text)
        params = fn.get("params", [])
        for p in params:
            if p not in ph:
                fail(f"{fn_name}: param '{p}' not found in SQL placeholders of {sql_path}")
        missing = sorted(ph - set(params))
        if missing:
            fail(f"{fn_name}: SQL has undeclared placeholders {missing} (add to configs/queries.yaml params)")

    glue_ph = extract_placeholders(glue_sql_raw)

    # 2) engine YAML keys exist (solana)
    sol = engine.get("chain_defaults", {}).get("solana")
    if not sol:
        fail("configs/golden_exit_engine.yaml: missing chain_defaults.solana")

    retention = engine.get("retention", {})
    for k in (
        "signals_raw_ttl_days",
        "trade_attempts_ttl_days",
        "rpc_events_ttl_days",
        "microticks_ttl_days",
        "forensics_ttl_days",
        "trades_ttl_days",
    ):
        if k not in retention:
            fail(f"configs/golden_exit_engine.yaml: missing retention.{k}")

    mode_thr = sol.get("mode_thresholds_sec", {})
    for k in ("U", "S", "M"):
        if k not in mode_thr:
            fail(f"mode_thresholds_sec missing {k}")

    eps = sol.get("epsilon", {})
    if "pad_ms_default" not in eps:
        fail("epsilon.pad_ms_default missing")
    hb = eps.get("hard_bounds_ms", {})
    if "min" not in hb or "max" not in hb:
        fail("epsilon.hard_bounds_ms min/max missing")

    clamp = sol.get("planned_hold", {}).get("clamp_sec", {})
    if "min_hold_sec" not in clamp or "max_hold_sec" not in clamp:
        fail("planned_hold.clamp_sec min/max missing")

    ag = sol.get("aggr_triggers", {})
    for k in ("U", "S", "M", "L"):
        if k not in ag or "window_s" not in ag[k] or "pct" not in ag[k]:
            fail(f"aggr_triggers.{k} missing window_s/pct")

    micro = sol.get("microticks", {})
    if "window_sec" not in micro:
        fail("microticks.window_sec missing")

    # 3) glue query placeholders must include all config-bound parameters
    required = {
        "epsilon_pad_ms",
        "epsilon_min_ms",
        "epsilon_max_ms",
        "margin_mult",
        "min_hold_sec",
        "max_hold_sec",
        "mode_u_max_sec",
        "mode_s_max_sec",
        "mode_m_max_sec",
        "microticks_window_s",
        "aggr_u_window_s",
        "aggr_u_pct",
        "aggr_s_window_s",
        "aggr_s_pct",
        "aggr_m_window_s",
        "aggr_m_pct",
        "aggr_l_window_s",
        "aggr_l_pct",
    }
    missing = sorted(required - glue_ph)
    if missing:
        fail(f"queries/04_glue_select.sql missing required placeholders: {missing}")

    # 4) Variant A: no hardcoded numeric literals equal to YAML thresholds in glue SQL
    bad_literals = [
        ("mode_u_max_sec", int(mode_thr["U"])),
        ("mode_s_max_sec", int(mode_thr["S"])),
        ("mode_m_max_sec", int(mode_thr["M"])),
        ("epsilon_pad_ms_default", int(eps["pad_ms_default"])),
        ("epsilon_min", int(hb["min"])),
        ("epsilon_max", int(hb["max"])),
        ("min_hold_sec", int(clamp["min_hold_sec"])),
        ("max_hold_sec", int(clamp["max_hold_sec"])),
        ("aggr_U_window", int(ag["U"]["window_s"])),
        ("aggr_S_window", int(ag["S"]["window_s"])),
        ("aggr_M_window", int(ag["M"]["window_s"])),
        ("aggr_L_window", int(ag["L"]["window_s"])),
        ("microticks_window_sec", int(micro["window_sec"])),
    ]
    for name, val in bad_literals:
        pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(str(val))}(?![A-Za-z0-9_])")
        if pat.search(glue_sql):
            fail(
                f"queries/04_glue_select.sql contains hardcoded literal '{val}' ({name}). Must be parameterized."
            )

    # 5) base quantile mapping contract: YAML must match SQL implementation
    base_map = sol.get("base_quantile_by_mode", {})
    expected = {"U": "q10_hold_sec", "S": "q25_hold_sec", "M": "q40_hold_sec", "L": "median_hold_sec"}
    if base_map != expected:
        fail(f"base_quantile_by_mode must equal {expected}, got {base_map}")

    for token in (
        "mode = 'U'",
        "p.q10_hold_sec",
        "mode = 'S'",
        "p.q25_hold_sec",
        "mode = 'M'",
        "p.q40_hold_sec",
        "p.median_hold_sec",
    ):
        if token not in glue_sql_raw:
            fail(f"queries/04_glue_select.sql missing mapping token: {token}")

    # 6) DDL retention TTL must match YAML retention
    ddl = read_text(CH_DDL)

    def check_table_ttl(table: str, yaml_days: int) -> None:
        block = ddl_block(ddl, table)
        d = ttl_days(block)
        if yaml_days == 0:
            if d is not None:
                fail(f"schemas/clickhouse.sql: table '{table}' must NOT have TTL when retention.{table}_ttl_days==0")
            return
        if d is None:
            fail(f"schemas/clickhouse.sql: table '{table}' missing TTL; expected {yaml_days} days")
        if int(d) != int(yaml_days):
            fail(f"schemas/clickhouse.sql: TTL mismatch for '{table}': DDL={d} days, YAML={yaml_days} days")

    check_table_ttl("signals_raw", int(retention["signals_raw_ttl_days"]))
    check_table_ttl("trade_attempts", int(retention["trade_attempts_ttl_days"]))
    check_table_ttl("rpc_events", int(retention["rpc_events_ttl_days"]))
    check_table_ttl("microticks_1s", int(retention["microticks_ttl_days"]))
    check_table_ttl("forensics_events", int(retention["forensics_ttl_days"]))

    # Special: trades TTL
    trades_days = int(retention["trades_ttl_days"])
    trades_block = ddl_block(ddl, "trades")
    trades_ttl = ttl_days(trades_block)
    if trades_days == 0 and trades_ttl is not None:
        fail("schemas/clickhouse.sql: trades must NOT have TTL when retention.trades_ttl_days==0")
    if trades_days != 0 and trades_ttl != trades_days:
        fail(f"schemas/clickhouse.sql: trades TTL mismatch: DDL={trades_ttl}, YAML={trades_days}")

    # 7) docs/CONTRACT_MATRIX must mention YAML + anti-drift rules
    cm = read_text(CONTRACT_MATRIX)
    for must in (
        "configs/golden_exit_engine.yaml",
        "configs/queries.yaml",
        "retention",
        "Anti-drift",
        "Variant A",
    ):
        if must not in cm:
            fail(f"docs/CONTRACT_MATRIX.md missing required mention: {must}")

    print("[OK] anti-drift checks passed")


if __name__ == "__main__":
    main()
