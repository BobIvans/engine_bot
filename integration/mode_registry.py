"""Mode registry (Variant A).

This module centralizes how "modes" are discovered from strategy config YAML.

Design goals:
- Deterministic, side-effect free.
- Tolerant to legacy/partial shapes: invalid entries are skipped.
"""

from __future__ import annotations

from typing import Any, Dict


def _as_mapping_modes(obj: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(obj, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if not isinstance(v, dict):
            continue
        out[k] = dict(v)
    return out


def _as_list_modes(obj: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(obj, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in obj:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        cfg = dict(item)
        cfg.pop("name", None)
        out[name] = cfg
    return out


def resolve_modes(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Resolve modes from config into a normalized mapping.

    Supported layouts (in priority order):
      1) cfg["modes"] as mapping: {"U": {...}, ...}
      2) cfg["modes"] as list: [{"name": "U", ...}, ...]
      3) cfg["signals"]["modes"]["base_profiles"] as mapping or list

    Returns:
      Dict keyed by mode name, each value is a dict of mode params.
      If no modes found, returns {}.
    """
    if not isinstance(cfg, dict):
        return {}

    # (1) root-level mapping
    root_modes = cfg.get("modes")
    out = _as_mapping_modes(root_modes)
    if out:
        return out

    # (2) root-level list
    out = _as_list_modes(root_modes)
    if out:
        return out

    # (3) fallback nested path
    signals = cfg.get("signals")
    if not isinstance(signals, dict):
        return {}
    modes = signals.get("modes")
    if not isinstance(modes, dict):
        return {}
    base_profiles = modes.get("base_profiles")

    out = _as_mapping_modes(base_profiles)
    if out:
        return out
    return _as_list_modes(base_profiles)
