#!/usr/bin/env python3
"""integration/config_mapper.py

Iteration-1 objective: make the chain runnable end-to-end

    strategy/strategy.yaml (human-friendly)
        -> integration/runtime/golden_exit_engine.yaml (CANON schema)
        -> SQL04 params (strictly registry-driven)

Rules:
- vendor/gmee_canon/** is read-only (ZIP-2 v23 CANON)
- Strategy may use aliases (U_max, window_sec, up_pct, ...)
- Runtime config must match CANON schema as read by vendor/gmee_canon/gmee/config.py
- SQL04 param names must match vendor/gmee_canon/configs/queries.yaml:functions.glue_select.params
  (missing/extra => hard fail).

Usage:
  python3 -m integration.config_mapper \
    --strategy strategy/strategy.yaml \
    --out integration/runtime/golden_exit_engine.yaml

"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR = REPO_ROOT / "vendor" / "gmee_canon"


class ConfigError(RuntimeError):
    pass


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"YAML not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _dump_yaml(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _require(d: Mapping[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise ConfigError(f"Missing key '{key}' in {ctx}")
    return d[key]


def _as_int(x: Any, ctx: str) -> int:
    try:
        return int(x)
    except Exception as e:
        raise ConfigError(f"Expected int for {ctx}, got {x!r}") from e


def _as_float(x: Any, ctx: str) -> float:
    try:
        return float(x)
    except Exception as e:
        raise ConfigError(f"Expected float for {ctx}, got {x!r}") from e


def _canon_paths() -> tuple[Path, Path]:
    engine = VENDOR / "configs" / "golden_exit_engine.yaml"
    queries = VENDOR / "configs" / "queries.yaml"
    if not engine.exists():
        raise ConfigError(f"CANON engine cfg not found: {engine}")
    if not queries.exists():
        raise ConfigError(f"CANON queries registry not found: {queries}")
    return engine, queries


def _read_glue_select_registry_params(queries_yaml: Dict[str, Any]) -> list[str]:
    funcs = _require(queries_yaml, "functions", "vendor/gmee_canon/configs/queries.yaml")
    glue = _require(funcs, "glue_select", "queries.yaml:functions")
    params = _require(glue, "params", "queries.yaml:functions.glue_select")
    if not isinstance(params, list) or not all(isinstance(x, str) for x in params):
        raise ConfigError("functions.glue_select.params must be a list[str]")
    return params


def _map_strategy_to_canon_engine_cfg(
    canon_template: Dict[str, Any],
    strategy_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a NEW dict that matches CANON engine schema.

    We start from the CANON template and override only chain_defaults[chain].
    """

    out = copy.deepcopy(canon_template)
    strat = _require(strategy_cfg, "strategy", "strategy/strategy.yaml")

    chain = str(_require(strat, "chain", "strategy"))
    cd = _require(out, "chain_defaults", "CANON engine cfg")
    cd_chain = _require(cd, chain, f"CANON chain_defaults[{chain}]")

    # --- mode thresholds: accept both {U,S,M} and {U_max,S_max,M_max}
    mt = _require(strat, "mode_thresholds_sec", "strategy")
    U = mt.get("U", mt.get("U_max"))
    S = mt.get("S", mt.get("S_max"))
    M = mt.get("M", mt.get("M_max"))
    if U is None or S is None or M is None:
        raise ConfigError("mode_thresholds_sec must define U/S/M (or U_max/S_max/M_max)")
    cd_chain.setdefault("mode_thresholds_sec", {})
    cd_chain["mode_thresholds_sec"]["U"] = _as_int(U, "mode_thresholds_sec.U")
    cd_chain["mode_thresholds_sec"]["S"] = _as_int(S, "mode_thresholds_sec.S")
    cd_chain["mode_thresholds_sec"]["M"] = _as_int(M, "mode_thresholds_sec.M")

    # --- planned hold
    ph = _require(strat, "planned_hold", "strategy")
    margin = ph.get("margin_mult", ph.get("margin_mult_default"))
    if margin is not None:
        cd_chain.setdefault("planned_hold", {})
        cd_chain["planned_hold"]["margin_mult_default"] = _as_float(margin, "planned_hold.margin_mult")

    clamp = _require(ph, "clamp_sec", "strategy.planned_hold")
    min_hold = clamp.get("min_hold_sec", clamp.get("min"))
    max_hold = clamp.get("max_hold_sec", clamp.get("max"))
    if min_hold is None or max_hold is None:
        raise ConfigError("planned_hold.clamp_sec must define min/max (or min_hold_sec/max_hold_sec)")
    cd_chain.setdefault("planned_hold", {})
    cd_chain["planned_hold"].setdefault("clamp_sec", {})
    cd_chain["planned_hold"]["clamp_sec"]["min_hold_sec"] = _as_int(min_hold, "planned_hold.clamp_sec.min")
    cd_chain["planned_hold"]["clamp_sec"]["max_hold_sec"] = _as_int(max_hold, "planned_hold.clamp_sec.max")

    # --- epsilon
    eps = _require(strat, "epsilon", "strategy")
    pad_ms = eps.get("pad_ms", eps.get("pad_ms_default"))
    if pad_ms is not None:
        cd_chain.setdefault("epsilon", {})
        cd_chain["epsilon"]["pad_ms_default"] = _as_int(pad_ms, "epsilon.pad_ms")
    hb = _require(eps, "hard_bounds_ms", "strategy.epsilon")
    eps_min = hb.get("min", hb.get("min_ms", hb.get("epsilon_min_ms")))
    eps_max = hb.get("max", hb.get("max_ms", hb.get("epsilon_max_ms")))
    if eps_min is None or eps_max is None:
        raise ConfigError("epsilon.hard_bounds_ms must define min/max")
    cd_chain.setdefault("epsilon", {})
    cd_chain["epsilon"].setdefault("hard_bounds_ms", {})
    cd_chain["epsilon"]["hard_bounds_ms"]["min"] = _as_int(eps_min, "epsilon.hard_bounds_ms.min")
    cd_chain["epsilon"]["hard_bounds_ms"]["max"] = _as_int(eps_max, "epsilon.hard_bounds_ms.max")

    # --- microticks window
    micro = _require(strat, "microticks", "strategy")
    micro_window = micro.get("window_sec", micro.get("window_s"))
    if micro_window is None:
        raise ConfigError("microticks must define window_sec (or window_s)")
    cd_chain.setdefault("microticks", {})
    cd_chain["microticks"]["window_sec"] = _as_int(micro_window, "microticks.window_sec")

    # --- aggr triggers (U/S/M/L)
    ag = _require(strat, "aggr_triggers", "strategy")
    cd_chain.setdefault("aggr_triggers", {})
    for mode in ("U", "S", "M", "L"):
        m = _require(ag, mode, f"strategy.aggr_triggers.{mode}")
        window = m.get("window_s", m.get("window_sec"))
        pct = m.get("pct", m.get("up_pct"))
        if window is None or pct is None:
            raise ConfigError(f"aggr_triggers.{mode} must define window_s/pct (or window_sec/up_pct)")
        cd_chain["aggr_triggers"][mode] = {
            "window_s": _as_int(window, f"aggr_triggers.{mode}.window"),
            "pct": _as_float(pct, f"aggr_triggers.{mode}.pct"),
        }

    return out


def _validate_sql04_params_against_registry(
    merged_engine_cfg: Dict[str, Any],
    *,
    chain: str,
    queries_registry: Sequence[str],
) -> None:
    """Validate that engine cfg can produce exactly the registry params (minus chain/trade_id)."""

    # Import CANON helper (read-only vendor)
    import sys

    sys.path.insert(0, str(VENDOR))
    from gmee.config import glue_select_params_from_cfg  # type: ignore

    engine_params = glue_select_params_from_cfg(merged_engine_cfg, chain)

    reg = list(queries_registry)
    reg_without_runtime = [p for p in reg if p not in ("chain", "trade_id")]

    missing = sorted(set(reg_without_runtime) - set(engine_params.keys()))
    extra = sorted(set(engine_params.keys()) - set(reg_without_runtime))
    if missing or extra:
        raise ConfigError(
            "SQL04 params mismatch vs registry. "
            f"missing={missing} extra={extra}\n"
            "(Registry: vendor/gmee_canon/configs/queries.yaml:functions.glue_select.params)"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default=str(REPO_ROOT / "strategy" / "strategy.yaml"))
    ap.add_argument("--out", default=str(REPO_ROOT / "integration" / "runtime" / "golden_exit_engine.yaml"))
    ap.add_argument("--canon-engine", default="")
    ap.add_argument("--canon-queries", default="")
    args = ap.parse_args()

    canon_engine, canon_queries = _canon_paths()
    if args.canon_engine:
        canon_engine = Path(args.canon_engine)
    if args.canon_queries:
        canon_queries = Path(args.canon_queries)

    strategy_path = Path(args.strategy)
    out_path = Path(args.out)

    canon_template = _load_yaml(canon_engine)
    strategy_cfg = _load_yaml(strategy_path)

    merged = _map_strategy_to_canon_engine_cfg(canon_template, strategy_cfg)

    # Validate we can generate params strictly by registry
    queries_yaml = _load_yaml(canon_queries)
    registry = _read_glue_select_registry_params(queries_yaml)

    chain = str(_require(_require(strategy_cfg, "strategy", "strategy"), "chain", "strategy.chain"))
    _validate_sql04_params_against_registry(merged, chain=chain, queries_registry=registry)

    _dump_yaml(merged, out_path)
    print(f"OK wrote CANON runtime engine cfg: {out_path}")
    print(f"Validated SQL04 params vs registry: {canon_queries}")


if __name__ == "__main__":
    main()

