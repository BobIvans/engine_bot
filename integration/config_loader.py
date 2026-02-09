#!/usr/bin/env python3
"""integration/config_loader.py

Runtime config loader for strategy-owned YAML in strategy/config/**.

Design goals:
- No CANON changes.
- No extra deps beyond PyYAML (already in requirements.txt).
- Deterministic config hash (sha256 of file bytes) to log into forensics_events.

This is intentionally "thin": it validates only a minimal contract so the runner can start.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedConfig:
    path: str
    config: Dict[str, Any]
    config_hash: str  # sha256 hex
    strategy_name: str
    version: str


def _sha256_file(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha256(b).hexdigest()


def _require(d: Dict[str, Any], key: str) -> Any:
    if key not in d:
        raise ConfigError(f"Missing required key: {key}")
    return d[key]


def load_params_base(path: str = "strategy/config/params_base.yaml") -> LoadedConfig:
    """Load and minimally validate the strategy runtime config."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config not found: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("params_base.yaml must be a YAML mapping (dict at top-level)")

    version = str(_require(raw, "version"))
    strategy_name = str(_require(raw, "strategy_name"))

    run = _require(raw, "run")
    if not isinstance(run, dict):
        raise ConfigError("run must be a mapping")

    mode = run.get("mode", "paper")
    if mode not in ("paper", "sim", "live"):
        raise ConfigError(f"run.mode must be one of paper|sim|live, got: {mode}")

    # Minimal subtrees expected by the iteration docs.
    for subtree in ("wallet_profile", "token_profile", "signals", "risk", "execution"):
        if subtree not in raw:
            raise ConfigError(f"Missing required subtree: {subtree}")

    return LoadedConfig(
        path=str(p),
        config=raw,
        config_hash=_sha256_file(p),
        strategy_name=strategy_name,
        version=version,
    )


# -------------------------------------------------------------------------
# Hot-Reload Integration (PR-Y.5)
# -------------------------------------------------------------------------

from typing import Optional
from config.hot_reload import ConfigReloader
from config.runtime_schema import RuntimeConfig

_RELOADER: Optional[ConfigReloader] = None
_STATIC_RUNTIME_CONFIG: Optional[RuntimeConfig] = None


def init_reloader(path: str, hot_reload: bool = False) -> None:
    """Initialize the configuration reloader singleton."""
    global _RELOADER, _STATIC_RUNTIME_CONFIG
    
    if hot_reload:
        # Start hot-reload watcher
        _RELOADER = ConfigReloader(path)
        _RELOADER.start_watching()
    else:
        # Load once and cache as static
        _RELOADER = None
        # We need to load the file to get RuntimeConfig defaults or values
        # We can reuse ConfigReloader logic temporarily or just load
        try:
             # Use the reloader's validation logic to ensure consistency
             loader = ConfigReloader(path)
             _STATIC_RUNTIME_CONFIG = loader.get_config()
             loader.stop_watching() # Just to be safe, though not started
        except Exception:
             # Fallback to defaults if file missing or invalid (though load_params_base should have caught it)
             _STATIC_RUNTIME_CONFIG = RuntimeConfig()


def get_runtime_config() -> RuntimeConfig:
    """Get the current runtime configuration (thread-safe)."""
    if _RELOADER:
        conf = _RELOADER.get_config()
        if conf:
            return conf
    
    if _STATIC_RUNTIME_CONFIG:
        return _STATIC_RUNTIME_CONFIG
        
    return RuntimeConfig()


def stop_reloader() -> None:
    """Stop the reloader thread if running."""
    if _RELOADER:
        _RELOADER.stop_watching()


def apply_runtime_overrides(base_cfg: Dict[str, Any], runtime: RuntimeConfig) -> Dict[str, Any]:
    """Apply runtime configuration overrides to the base config dictionary.
    
    Returns a new dictionary with overrides applied (shallow copy).
    """
    new_cfg = base_cfg.copy()
    
    # Signals
    if "signals" not in new_cfg:
        new_cfg["signals"] = {}
    # Ensure nested dict copy if we modify it
    new_cfg["signals"] = new_cfg["signals"].copy()
    new_cfg["signals"]["edge_threshold_base"] = runtime.edge_threshold_base
    new_cfg["signals"]["edge_threshold_riskon"] = runtime.edge_threshold_riskon
    new_cfg["signals"]["edge_threshold_riskoff"] = runtime.edge_threshold_riskoff

    # Risk
    if "risk" not in new_cfg:
        new_cfg["risk"] = {}
    new_cfg["risk"] = new_cfg["risk"].copy()
    
    # Sizing
    if "sizing" not in new_cfg["risk"]:
        new_cfg["risk"]["sizing"] = {}
    new_cfg["risk"]["sizing"] = new_cfg["risk"]["sizing"].copy()
    
    new_cfg["risk"]["sizing"]["fixed_pct_of_bankroll"] = runtime.position_pct
    new_cfg["risk"]["sizing"]["kelly_fraction"] = runtime.kelly_fraction
    
    # Limits
    if "limits" not in new_cfg["risk"]:
        new_cfg["risk"]["limits"] = {}
    new_cfg["risk"]["limits"] = new_cfg["risk"]["limits"].copy()
    
    new_cfg["risk"]["limits"]["max_open_positions"] = runtime.max_open_positions
    new_cfg["risk"]["limits"]["max_exposure_per_token_pct"] = runtime.max_token_exposure
    new_cfg["risk"]["limits"]["max_daily_loss_pct"] = runtime.max_daily_loss
    
    # Cooldown
    if "cooldown" not in new_cfg["risk"]["limits"]:
        new_cfg["risk"]["limits"]["cooldown"] = {}
    new_cfg["risk"]["limits"]["cooldown"] = new_cfg["risk"]["limits"]["cooldown"].copy()
    
    new_cfg["risk"]["limits"]["cooldown"]["duration_sec"] = runtime.cooldown_after_losses_sec
    
    return new_cfg
