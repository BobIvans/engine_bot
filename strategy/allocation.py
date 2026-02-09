"""
strategy/allocation.py

Dynamic Mode Allocation (Bankroll Splitter).

Allocates capital between trading modes (U/S/M/L/Cash) based on
volatility and regime scores.

PR-V.3
"""
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


# Regime threshold for risk-off (bearish market)
BEARISH_THRESHOLD = -0.3

# Volatility thresholds
LOW_VOL_THRESHOLD = 0.3
HIGH_VOL_THRESHOLD = 0.7

# Minimum allocation to any mode (excluding cash)
MIN_MODE_ALLOCATION = 0.0


@dataclass
class AllocationConfig:
    """Configuration for mode allocation."""
    # Base weights for each mode (U=Ultra, S=Short, M=Medium, L=Long, C=Cash)
    base_weights: Dict[str, float]
    
    # Volatility modifier strength (0-1)
    vol_sensitivity: float = 0.5
    
    # Regime modifier strength (0-1)
    regime_sensitivity: float = 0.5
    
    # Minimum allocation percentage for any mode
    min_weight: float = 0.0
    
    # Cash buffer when in bearish regime
    cash_buffer_bearish: float = 0.5
    
    # Risk-on mode names (higher allocation in high volatility)
    risk_on_modes: List[str] = None
    
    # Risk-off mode names (higher allocation in low volatility)
    risk_off_modes: List[str] = None
    
    def __post_init__(self):
        if self.risk_on_modes is None:
            self.risk_on_modes = ['U', 'S']
        if self.risk_off_modes is None:
            self.risk_off_modes = ['M', 'L', 'C']


@dataclass
class AllocationResult:
    """Result of allocation computation."""
    allocations: Dict[str, float]  # Mode -> USD amount
    version: str = "v1"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "allocations": self.allocations,
        }


class ModeAllocator:
    """
    Pure logic for computing mode allocations.
    
    PR-V.3
    """
    
    # Version tag for output format
    OUTPUT_VERSION = "v1"
    
    def __init__(self, config: AllocationConfig):
        """
        Initialize allocator with configuration.
        
        Args:
            config: AllocationConfig with base weights and sensitivity settings
        """
        self.config = config
    
    def compute_allocation(
        self,
        total_equity_usd: float,
        volatility_score: float,
        regime_score: float,
    ) -> AllocationResult:
        """
        Compute allocation plan for given market conditions.
        
        Args:
            total_equity_usd: Total capital to allocate
            volatility_score: Normalized volatility (0-1)
            regime_score: Market regime score (-1 to 1)
                          -1 = Bearish, 0 = Neutral, 1 = Bullish
            
        Returns:
            AllocationResult with mode allocations
        """
        # Step 1: Apply regime modifier
        # In bearish regime, shift towards cash
        weights = self._apply_regime_modifier(
            self.config.base_weights.copy(),
            regime_score
        )
        
        # Step 2: Apply volatility modifier
        # In high volatility, shift towards U/S modes
        weights = self._apply_volatility_modifier(
            weights,
            volatility_score
        )
        
        # Step 3: Normalize weights to sum to 1.0
        weights = self._normalize_weights(weights)
        
        # Step 4: Apply minimum allocation constraints
        weights = self._apply_min_constraints(weights)
        
        # Step 5: Normalize again after constraints
        weights = self._normalize_weights(weights)
        
        # Step 6: Convert weights to USD amounts
        allocations = {
            mode: round(weight * total_equity_usd, 2)
            for mode, weight in weights.items()
        }
        
        # Ensure total matches equity (allocation_plan.v1 format)
        allocated = sum(allocations.values())
        if allocated != total_equity_usd:
            # Adjust cash to match exactly
            diff = total_equity_usd - allocated
            if 'C' in allocations:
                allocations['C'] = round(allocations['C'] + diff, 2)
            elif 'cash' in allocations:
                allocations['cash'] = round(allocations['cash'] + diff, 2)
        
        return AllocationResult(
            allocations=allocations,
            version=self.OUTPUT_VERSION,
        )
    
    def _apply_regime_modifier(
        self,
        weights: Dict[str, float],
        regime_score: float,
    ) -> Dict[str, float]:
        """
        Apply regime-based weight modifications.
        
        In bearish regime:
        - Reduce U/S weights
        - Increase cash weight
        """
        modifier = self.config.regime_sensitivity
        
        # Calculate regime factor (1.0 for bullish, 0.0 for very bearish)
        regime_factor = (regime_score + 1) / 2  # Convert -1..1 to 0..1
        
        # Bearish regime check
        is_bearish = regime_score < BEARISH_THRESHOLD
        
        for mode in weights:
            if mode in ['C', 'cash']:
                # Cash gets more weight in bearish regime
                if is_bearish:
                    # Increase cash based on how bearish it is
                    cash_boost = self.config.cash_buffer_bearish * (1 - regime_factor)
                    weights[mode] = min(1.0, weights[mode] * (1 + cash_boost * modifier))
            else:
                # Risky modes get less weight in bearish regime
                if is_bearish:
                    weights[mode] = weights[mode] * regime_factor * (1 - modifier * 0.5)
        
        return weights
    
    def _apply_volatility_modifier(
        self,
        weights: Dict[str, float],
        volatility_score: float,
    ) -> Dict[str, float]:
        """
        Apply volatility-based weight modifications.
        
        In high volatility:
        - Increase U/S weights
        - Decrease M/L weights
        """
        modifier = self.config.vol_sensitivity
        
        # Volatility factor (0-1)
        vol_factor = volatility_score
        
        # Shift factor based on volatility
        shift = (vol_factor - 0.5) * 2 * modifier  # -modifier to +modifier
        
        for mode in weights:
            if mode in self.config.risk_on_modes:
                # Risk-on modes get more weight in high vol
                weights[mode] = weights[mode] * (1 + shift)
            elif mode in self.config.risk_off_modes and mode not in ['C', 'cash']:
                # Risk-off modes (except cash) get less weight in high vol
                weights[mode] = weights[mode] * (1 - shift * 0.5)
        
        return weights
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normalize weights to sum to 1.0."""
        total = sum(weights.values())
        if total == 0:
            # If all weights are zero, return equal weights
            return {k: 1.0 / len(weights) for k in weights}
        return {k: v / total for k, v in weights.items()}
    
    def _apply_min_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Apply minimum allocation constraints."""
        min_w = self.config.min_weight
        
        # First, apply minimum to each mode
        for mode in weights:
            weights[mode] = max(weights[mode], min_w)
        
        return weights


def compute_allocation(
    total_equity_usd: float,
    volatility_score: float,
    regime_score: float,
    config: AllocationConfig,
) -> AllocationResult:
    """
    Convenience function for computing allocation.
    
    This is a pure function - same inputs always produce same outputs.
    
    Args:
        total_equity_usd: Total capital to allocate
        volatility_score: Normalized volatility (0-1)
        regime_score: Market regime score (-1 to 1)
        config: AllocationConfig with base weights
        
    Returns:
        AllocationResult with mode allocations
    """
    allocator = ModeAllocator(config)
    return allocator.compute_allocation(
        total_equity_usd,
        volatility_score,
        regime_score,
    )
