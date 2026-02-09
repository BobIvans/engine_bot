from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

from typing import Any, Mapping

import yaml

from .util import stable_json_dumps, sha256_hex


def load_engine_config(path: str | Path = "configs/golden_exit_engine.yaml") -> dict[str, Any]:
    """Load canonical engine config YAML."""
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def compute_config_hash(cfg: Mapping[str, Any]) -> str:
    """Compute FixedString(64) config_hash from loaded YAML."""
    # Hash the full YAML object in canonical JSON form.
    return sha256_hex(stable_json_dumps(cfg).encode("utf-8"))


def chain_params(cfg: Mapping[str, Any], chain: str) -> dict[str, Any]:
    """Extract chain_defaults parameters for glue_select mapping."""
    defaults = cfg.get("chain_defaults", {})
    if chain not in defaults:
        raise KeyError(f"chain_defaults missing for chain={chain!r}")
    return defaults[chain]


def glue_select_params_from_cfg(cfg: Mapping[str, Any], chain: str) -> dict[str, Any]:
    """Build Variant A glue_select parameter dict from configs/golden_exit_engine.yaml."""
    sol = chain_params(cfg, chain)
    params = {
        "epsilon_pad_ms": int(sol["epsilon"]["pad_ms_default"]),
        "epsilon_min_ms": int(sol["epsilon"]["hard_bounds_ms"]["min"]),
        "epsilon_max_ms": int(sol["epsilon"]["hard_bounds_ms"]["max"]),
        "margin_mult": float(sol["planned_hold"]["margin_mult_default"]),
        "min_hold_sec": int(sol["planned_hold"]["clamp_sec"]["min_hold_sec"]),
        "max_hold_sec": int(sol["planned_hold"]["clamp_sec"]["max_hold_sec"]),
        "mode_u_max_sec": int(sol["mode_thresholds_sec"]["U"]),
        "mode_s_max_sec": int(sol["mode_thresholds_sec"]["S"]),
        "mode_m_max_sec": int(sol["mode_thresholds_sec"]["M"]),
        "microticks_window_s": int(sol["microticks"]["window_sec"]),
        "aggr_u_window_s": int(sol["aggr_triggers"]["U"]["window_s"]),
        "aggr_u_pct": float(sol["aggr_triggers"]["U"]["pct"]),
        "aggr_s_window_s": int(sol["aggr_triggers"]["S"]["window_s"]),
        "aggr_s_pct": float(sol["aggr_triggers"]["S"]["pct"]),
        "aggr_m_window_s": int(sol["aggr_triggers"]["M"]["window_s"]),
        "aggr_m_pct": float(sol["aggr_triggers"]["M"]["pct"]),
        "aggr_l_window_s": int(sol["aggr_triggers"]["L"]["window_s"]),
        "aggr_l_pct": float(sol["aggr_triggers"]["L"]["pct"]),
    }
    return params
