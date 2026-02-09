"""Minimal, deterministic validator for strategy YAML configs.

Design goals:
- No side effects.
- CI-friendly error messages (stderr only, each line starts with 'ERROR:').
- Exit codes:
  - 0: valid
  - 2: validation errors
  - 1: runtime errors (file missing / YAML parse failure)

Supports two common shapes for mode configuration without forcing a
refactor of existing YAML:

1) Root-level `modes`:

   modes:
     U: { ttl_sec: 60, ... }

   or

   modes:
     - { name: U, ttl_sec: 60, ... }

2) Existing repo shape: `signals.modes.base_profiles` mapping.

Only stderr is used for messaging; stdout remains silent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml


EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_INVALID = 2


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _is_int(x: Any) -> bool:
    # bool is a subclass of int; treat it as not-an-int for config values
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _find_modes_root(cfg: Mapping[str, Any]) -> Optional[Any]:
    if "modes" in cfg:
        return cfg.get("modes")
    # Back-compat with current repo config layout.
    cur: Any = cfg
    for k in ("signals", "modes", "base_profiles"):
        if not isinstance(cur, Mapping) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _iter_modes(modes_obj: Any, errors: List[str]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    """Yield (mode_name, mode_cfg) pairs or add validation errors."""

    if isinstance(modes_obj, Mapping):
        for name, obj in modes_obj.items():
            if not isinstance(name, str) or not name.strip():
                errors.append("ERROR: modes.<mode_name> must be an object")
                continue
            if not isinstance(obj, Mapping):
                errors.append(f"ERROR: modes.{name} must be an object")
                continue
            yield name, obj
        return

    if isinstance(modes_obj, list):
        for i, item in enumerate(modes_obj):
            if not isinstance(item, Mapping):
                errors.append(f"ERROR: modes[{i}] must be an object")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"ERROR: modes[{i}].name must be a non-empty string")
                continue
            yield name, item
        return

    errors.append("ERROR: Key 'modes' must be a list or mapping")


def validate_config(cfg: Any) -> List[str]:
    errors: List[str] = []

    if not isinstance(cfg, Mapping):
        errors.append("ERROR: Config root must be a mapping/object")
        return errors

    modes_obj = _find_modes_root(cfg)
    if modes_obj is None:
        errors.append("ERROR: Missing required key: modes")
        return errors

    seen: set[str] = set()
    for name, mode in _iter_modes(modes_obj, errors):
        if name in seen:
            errors.append(f"ERROR: Duplicate mode name: {name}")
            continue
        seen.add(name)

        # ttl_sec: required, int > 0
        ttl_sec = mode.get("ttl_sec")
        if not _is_int(ttl_sec) or ttl_sec <= 0:
            errors.append(f"ERROR: mode '{name}': ttl_sec must be an integer > 0")

        # max_slippage_bps: optional for now (not present in current params_base.yaml)
        if "max_slippage_bps" in mode:
            msb = mode.get("max_slippage_bps")
            if not _is_int(msb) or msb < 0:
                errors.append(
                    f"ERROR: mode '{name}': max_slippage_bps must be an integer >= 0"
                )

        # tp_pct / sl_pct
        tp_pct = mode.get("tp_pct")
        if not _is_number(tp_pct) or float(tp_pct) <= 0.0:
            errors.append(f"ERROR: mode '{name}': tp_pct must be a number > 0")

        sl_pct = mode.get("sl_pct")
        if not _is_number(sl_pct) or float(sl_pct) >= 0.0:
            errors.append(f"ERROR: mode '{name}': sl_pct must be a number < 0")

        # hold_sec_min / hold_sec_max
        hmin = mode.get("hold_sec_min")
        if not _is_int(hmin) or hmin < 0:
            errors.append(f"ERROR: mode '{name}': hold_sec_min must be an integer >= 0")

        hmax = mode.get("hold_sec_max")
        if not _is_int(hmax) or hmax < 0:
            errors.append(f"ERROR: mode '{name}': hold_sec_max must be an integer >= 0")

        if _is_int(hmin) and _is_int(hmax) and hmax < hmin:
            errors.append(f"ERROR: mode '{name}': hold_sec_max must be >= hold_sec_min")

    return errors


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        _eprint(f"ERROR: Config file not found: {cfg_path}")
        return EXIT_RUNTIME

    try:
        raw = cfg_path.read_text(encoding="utf-8")
    except Exception as e:
        # Existence is checked above; avoid duplicating "not found" on read errors.
        _eprint(f"ERROR: Failed to read config: {type(e).__name__}: {e}")
        return EXIT_RUNTIME

    try:
        cfg = yaml.safe_load(raw)
    except Exception as e:
        _eprint(f"ERROR: Failed to parse YAML: {cfg_path}: {type(e).__name__}: {e}")
        return EXIT_RUNTIME

    errors = validate_config(cfg)
    if errors:
        for msg in errors:
            _eprint(msg)
        _eprint(f"ERROR: Config validation failed: {len(errors)} error(s)")
        return EXIT_INVALID

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
