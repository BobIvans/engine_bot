"""config/hot_reload.py

Thread-safe configuration reloader with file watching.
"""

import time
import threading
import dataclasses
import yaml
import copy
import logging
from pathlib import Path
from typing import Callable, Optional, Dict, Any

from config.runtime_schema import RuntimeConfig

logger = logging.getLogger(__name__)


class ConfigReloader:
    """
    Watches a configuration file for changes and atomically updates valid runtime parameters.
    """

    def __init__(
        self, 
        config_path: str, 
        on_reload: Optional[Callable[[RuntimeConfig], None]] = None
    ):
        self._config_path = Path(config_path)
        self._on_reload = on_reload
        
        # Internal state
        self._current_config: Optional[RuntimeConfig] = None
        self._last_mtime: float = 0.0
        self._lock = threading.RLock()
        
        # Threading
        self._stop_event = threading.Event()
        self._watcher_thread: Optional[threading.Thread] = None

        # Initial load
        if self._config_path.exists():
            self._load_initial()
        else:
            logger.warning(f"Config file not found at {self._config_path}, waiting for creation.")

    def _load_initial(self) -> None:
        """Load config synchronously on startup."""
        try:
            new_conf = self._read_and_validate()
            with self._lock:
                self._current_config = new_conf
                self._last_mtime = self._config_path.stat().st_mtime
            logger.info(f"[config] Initial configuration loaded from {self._config_path}")
        except Exception as e:
            logger.error(f"[config] Failed to load initial config: {e}")
            # We don't crash here; caller might handle or we start with defaults/None
            # If strictly required, caller should check get_config()

    def get_config(self) -> Optional[RuntimeConfig]:
        """Thread-safe access to current configuration snapshot."""
        with self._lock:
            # Return immutable copy (RuntimeConfig is frozen, so just ref is fine, but for safety in case of mutable fields in future)
            return self._current_config

    def start_watching(self) -> None:
        """Start the background watcher thread."""
        if self._watcher_thread is not None:
            return
            
        self._stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._poll_loop, 
            name="ConfigWatcher",
            daemon=True
        )
        self._watcher_thread.start()
        logger.info(f"[config] Started watching {self._config_path} for changes...")

    def stop_watching(self) -> None:
        """Stop the background watcher thread."""
        self._stop_event.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=2.0)
            self._watcher_thread = None
        logger.info("[config] Stopped config watcher.")

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_file()
            except Exception as e:
                logger.error(f"[config] Error in watcher loop: {e}")
            
            # Sleep in small chunks to be responsive to stop_event
            for _ in range(10): 
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

    def _check_file(self) -> None:
        if not self._config_path.exists():
            return

        try:
            current_mtime = self._config_path.stat().st_mtime
            # Using inequality to catch both updates and replacements/reverts
            if current_mtime != self._last_mtime:
                # Wait a bit for file write to settle (atomic moves are instant, but direct writes might flicker)
                time.sleep(0.1) 
                
                # Check again if mtime changed during reliable sleep, or assume stable
                # We simply reload.
                self._try_reload(current_mtime)
        except OSError:
            pass  # File transiently unavailable

    def _try_reload(self, new_mtime: float) -> None:
        try:
            logger.info(f"[config] Detected change in {self._config_path}, reloading...")
            new_conf = self._read_and_validate()
            
            with self._lock:
                old_conf = self._current_config
                self._current_config = new_conf
                self._last_mtime = new_mtime

            # Log changes
            if old_conf:
                changes = []
                # Use dataclasses.fields instead of pydantic model_fields
                for f in dataclasses.fields(RuntimeConfig):
                    field_name = f.name
                    old_val = getattr(old_conf, field_name)
                    new_val = getattr(new_conf, field_name)
                    if old_val != new_val:
                        changes.append(f"{field_name} {old_val} -> {new_val}")
                if changes:
                    logger.info(f"[config] Reloaded: {', '.join(changes)}")
                else:
                    logger.info("[config] Reloaded (no runtime parameters changed).")
            else:
                logger.info("[config] Configuration loaded successfully.")

            # Notify listener
            if self._on_reload:
                self._on_reload(new_conf)

        except Exception as e:
            logger.error(f"[config] Reload FAILED: {e}. Keeping previous configuration.")
            # Do NOT update self._last_mtime so we retry if file is fixed (actually if file is touched again)
            # But if validation fails, mtime IS changed on disk. If we don't update _last_mtime, we loop trying to reload?
            # Yes, if mtime matches file, we retry in next loop.
            # To avoid tight loop on broken file, we SHOULD update _last_mtime?
            # Or we only update _last_mtime on SUCCESS.
            # If we don't update, we will spam errors every 1s.
            # Only update mtime if it was a file read error vs validation error?
            # Better strategy: update _last_mtime to current file mtime to acknowledge we SAW this version, even if bad.
            try:
                self._last_mtime = self._config_path.stat().st_mtime
            except OSError:
                pass


    def _read_and_validate(self) -> RuntimeConfig:
        with open(self._config_path, 'r') as f:
            raw_data = yaml.safe_load(f)
            
        if not isinstance(raw_data, dict):
            raise ValueError("Config root must be a dictionary")
            
        # Flatten nested structure to match RuntimeConfig schema
        # ConfigLoader expects full structure, RuntimeConfig extracts specific fields.
        
        flat_data = {}
        
        # Signals
        signals = raw_data.get("signals", {})
        if "edge_threshold_base" in signals:
            flat_data["edge_threshold_base"] = signals["edge_threshold_base"]
        if "edge_threshold_riskon" in signals:
            flat_data["edge_threshold_riskon"] = signals["edge_threshold_riskon"]
        if "edge_threshold_riskoff" in signals:
            flat_data["edge_threshold_riskoff"] = signals["edge_threshold_riskoff"]
            
        # Risk
        risk = raw_data.get("risk", {})
        
        # Direct risk fields? or inside nested?
        # RuntimeConfig has position_pct.
        # Check defaults if missing.
        
        # Map: runtime.position_pct -> risk.sizing.fixed_pct_of_bankroll (if exists)
        # OR risk.position_pct?
        # In my smoke test config I put usage in risk.sizing.fixed_pct_of_bankroll.
        
        # Let's try to find them in likely places.
        
        # position_pct
        if "position_pct" in risk:
            flat_data["position_pct"] = risk["position_pct"]
        elif "sizing" in risk and "fixed_pct_of_bankroll" in risk["sizing"]:
            flat_data["position_pct"] = risk["sizing"]["fixed_pct_of_bankroll"]
            
        # max_open_positions
        limits = risk.get("limits", {})
        if "max_open_positions" in limits:
            flat_data["max_open_positions"] = limits["max_open_positions"]
            
        # max_token_exposure
        if "max_exposure_per_token_pct" in limits:
            flat_data["max_token_exposure"] = limits["max_exposure_per_token_pct"]
            
        # max_daily_loss
        if "max_daily_loss_pct" in limits:
            flat_data["max_daily_loss"] = limits["max_daily_loss_pct"]
            
        # kelly_fraction
        sizing = risk.get("sizing", {})
        if "kelly_fraction" in sizing:
            flat_data["kelly_fraction"] = sizing["kelly_fraction"]
            
        # cooldown_after_losses_sec
        cooldown = limits.get("cooldown", {})
        if "duration_sec" in cooldown:
            flat_data["cooldown_after_losses_sec"] = cooldown["duration_sec"]

        # Note: If fields are missing here, Pydantic will use defaults from RuntimeConfig definition.
        # This is safe.
            
        return RuntimeConfig(**flat_data)
