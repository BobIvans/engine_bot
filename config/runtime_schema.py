"""config/runtime_schema.py

Defines the configuration schema for hot-reloadable parameters.
Only fields defined in RuntimeConfig are allowed to change at runtime.
Implements manual validation to avoid Pydantic dependency.
"""

from dataclasses import dataclass, field
from typing import Optional, Any

@dataclass(frozen=True)
class RuntimeConfig:
    """
    Whitelisted configuration parameters that can be updated at runtime.
    Changes to these fields will be applied immediately without restart.
    """
    # Signal Engine parameters
    edge_threshold_base: float = 0.05
    edge_threshold_riskon: float = 0.04
    edge_threshold_riskoff: float = 0.06
    
    # Risk Manager parameters
    position_pct: float = 0.02
    max_open_positions: int = 3
    max_token_exposure: float = 0.10
    max_daily_loss: float = 0.05
    kelly_fraction: float = 0.5
    cooldown_after_losses_sec: int = 300

    # Partial Fill Retry (PR-Z.2)
    partial_retry_enabled: bool = False
    partial_retry_max_attempts: int = 3
    partial_retry_size_decay: float = 0.7  # 100% -> 70% -> 49%
    partial_retry_fee_multiplier: float = 1.5  # fee * 1.5 per attempt
    partial_retry_ttl_sec: int = 120

    # Dynamic Trailing Stop (PR-Z.3)
    dynamic_trailing_enabled: bool = False
    trailing_base_distance_bps: int = 150  # Base distance in basis points (1.5%)
    trailing_volatility_multiplier: float = 1.8  # Expand × when RV high
    trailing_volume_multiplier: float = 0.9  # Contract × with confirming volume
    trailing_max_distance_bps: int = 500  # Hard cap for profit protection
    trailing_rv_threshold_high: float = 0.08  # RV 5m > 8% = high volatility
    trailing_rv_threshold_low: float = 0.03  # RV 5m < 3% = low volatility
    trailing_volume_confirm_threshold: float = 1.5  # Volume delta threshold

    # Coordination Detection (PR-Z.5)
    coordination_threshold: float = 0.7  # Threshold for high coordination score

    # Exit Hazard Prediction (PR-Z.4)
    hazard_threshold: float = 0.35  # Threshold for triggering aggressive exit

    def __post_init__(self):
        """Validate constraints manually since we don't have Pydantic."""
        # Signal Engine
        self._validate_range("edge_threshold_base", self.edge_threshold_base, 0.0, 1.0)
        self._validate_range("edge_threshold_riskon", self.edge_threshold_riskon, 0.0, 1.0)
        self._validate_range("edge_threshold_riskoff", self.edge_threshold_riskoff, 0.0, 1.0)
        
        # Risk Manager
        self._validate_range("position_pct", self.position_pct, 0.005, 0.05)
        self._validate_range("max_open_positions", self.max_open_positions, 1, 10)
        self._validate_range("max_token_exposure", self.max_token_exposure, 0.01, 0.50)
        self._validate_range("max_daily_loss", self.max_daily_loss, 0.01, 0.20)
        self._validate_range("kelly_fraction", self.kelly_fraction, 0.1, 1.0)
        self._validate_range("cooldown_after_losses_sec", self.cooldown_after_losses_sec, 0, None)

        # Partial Fill Retry
        if self.partial_retry_enabled:
            self._validate_range("partial_retry_max_attempts", self.partial_retry_max_attempts, 1, 5)
            self._validate_range("partial_retry_size_decay", self.partial_retry_size_decay, 0.5, 0.9)
            self._validate_range("partial_retry_fee_multiplier", self.partial_retry_fee_multiplier, 1.2, 3.0)
            self._validate_range("partial_retry_ttl_sec", self.partial_retry_ttl_sec, 30, 300)

        # Dynamic Trailing Stop
        if self.dynamic_trailing_enabled:
            self._validate_range("trailing_base_distance_bps", self.trailing_base_distance_bps, 50, 500)
            self._validate_range("trailing_volatility_multiplier", self.trailing_volatility_multiplier, 0.5, 3.0)
            self._validate_range("trailing_volume_multiplier", self.trailing_volume_multiplier, 0.5, 1.0)
            self._validate_range("trailing_max_distance_bps", self.trailing_max_distance_bps, 300, 1000)
            self._validate_range("trailing_rv_threshold_high", self.trailing_rv_threshold_high, 0.05, 0.15)
            self._validate_range("trailing_rv_threshold_low", self.trailing_rv_threshold_low, 0.01, 0.05)
            self._validate_range("trailing_volume_confirm_threshold", self.trailing_volume_confirm_threshold, 1.2, 3.0)

        # Coordination Detection
        self._validate_range("coordination_threshold", self.coordination_threshold, 0.5, 0.95)

        # Exit Hazard Prediction
        self._validate_range("hazard_threshold", self.hazard_threshold, 0.1, 0.7)

    def _validate_range(self, name: str, value: Any, min_val: float, max_val: Optional[float] = None) -> None:
        if not isinstance(value, (int, float)):
             # Allow int for float fields? usually yes in Python but let's be strict if needed.
             # Actually float(value) might be safer if coming from YAML.
             # But frozen dataclass sets attibutes before post_init?
             # Yes.
             pass
             
        try:
            val = float(value)
        except ValueError:
            raise ValueError(f"{name} must be numeric, got {value}")
            
        if val < min_val:
            raise ValueError(f"{name} {val} is below minimum {min_val}")
        if max_val is not None and val > max_val:
            raise ValueError(f"{name} {val} is above maximum {max_val}")


class MasterConfig(RuntimeConfig):
    """
    Full configuration schema including static fields.
    For type hinting mostly.
    """
    pass
