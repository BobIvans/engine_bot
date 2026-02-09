#!/usr/bin/env python3
"""Second line of defense: ban YAML-derived numeric literals inside queries/04_glue_select.sql (P0).

We do NOT do a blanket ban on numbers (would be flaky).
Instead we extract the relevant numeric values from configs/golden_exit_engine.yaml:
- thresholds (mode_thresholds_sec)
- epsilon (pad_ms_default, hard_bounds_ms)
- clamp (planned_hold.clamp_sec + margin_mult_default)
- aggr triggers (window_s, pct)
- microticks window (window_sec)

Then we assert that NONE of those values appear in queries/04_glue_select.sql as numeric literals.

Primary defense is scripts/assert_no_drift.py.
This guard is a cheap, independent backstop.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import yaml


SQL_PATH = Path("queries/04_glue_select.sql")
YAML_PATH = Path("configs/golden_exit_engine.yaml")
DEFAULT_CHAIN = "solana"


def _strip_sql_comments(sql: str) -> str:
    # Remove /* ... */ blocks
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove -- line comments
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    return sql


def _fmt_float(v: float) -> str:
    # stable minimal decimal string without scientific notation
    d = Decimal(str(v))
    s = format(d.normalize(), "f")
    # normalize can produce "0" for 0.0; keep at least one decimal point for floats
    if "." not in s:
        s = s + ".0"
    return s


def _num_patterns(v: Any) -> list[str]:
    """Return regex patterns that match the numeric literal value v with common formatting variants."""
    if isinstance(v, bool) or v is None:
        return []
    if isinstance(v, int):
        s = str(v)
        # match 150 or 150.0 or 150.00
        return [rf"{re.escape(s)}(?:\.0+)?"]
    if isinstance(v, float):
        s = _fmt_float(v)
        # allow trailing zeros after decimal
        if "." in s:
            base, frac = s.split(".", 1)
            if frac == "0":
                return [rf"{re.escape(base)}\.0+"]
            return [rf"{re.escape(base)}\.{re.escape(frac)}0*"]
        return [re.escape(s)]
    # fallback: try to parse as Decimal
    try:
        d = Decimal(str(v))
        s = format(d.normalize(), "f")
        if "." not in s:
            return [rf"{re.escape(s)}(?:\.0+)?"]
        base, frac = s.split(".", 1)
        return [rf"{re.escape(base)}\.{re.escape(frac)}0*"]
    except Exception:
        return []


def _extract_relevant_numbers(cfg: dict[str, Any], chain: str) -> list[Any]:
    sol = cfg.get("chain_defaults", {}).get(chain, {})
    out: list[Any] = []

    # thresholds
    out += list((sol.get("mode_thresholds_sec") or {}).values())

    # epsilon
    eps = sol.get("epsilon") or {}
    out.append(eps.get("pad_ms_default"))
    hb = eps.get("hard_bounds_ms") or {}
    out.append(hb.get("min"))
    out.append(hb.get("max"))

    # planned hold / clamp / margin
    ph = sol.get("planned_hold") or {}
    out.append(ph.get("margin_mult_default"))
    clamp = ph.get("clamp_sec") or {}
    out.append(clamp.get("min_hold_sec"))
    out.append(clamp.get("max_hold_sec"))

    # microticks
    mt = sol.get("microticks") or {}
    out.append(mt.get("window_sec"))

    # aggr triggers
    ag = sol.get("aggr_triggers") or {}
    for mode in ("U", "S", "M", "L"):
        m = ag.get(mode) or {}
        out.append(m.get("window_s"))
        out.append(m.get("pct"))

    # filter None
    out = [x for x in out if x is not None]
    return out


def main() -> int:
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    nums = _extract_relevant_numbers(cfg, DEFAULT_CHAIN)

    sql = _strip_sql_comments(SQL_PATH.read_text(encoding="utf-8"))

    banned_hits: list[str] = []
    for n in nums:
        for pat in _num_patterns(n):
            # enforce token-ish boundaries so 30 doesn't match 30d
            rx = re.compile(rf"(?<![A-Za-z0-9_\.]){pat}(?![A-Za-z0-9_\.])")
            if rx.search(sql):
                banned_hits.append(str(n))

    if banned_hits:
        uniq = sorted(set(banned_hits), key=lambda x: (len(x), x))
        print("YAML literal ban guard failed: found YAML-derived numeric literals in 04_glue_select.sql:")
        for v in uniq:
            print(f"  - {v}")
        return 2

    print("OK: no YAML-derived numeric literals found in queries/04_glue_select.sql")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
