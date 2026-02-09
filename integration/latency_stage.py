"""integration/latency_stage.py - Latency Integration Stage (PR-R.1)

Glue layer that measures network latency and injects latency cost
into the trading pipeline.

Pipeline flow:
1. Measure network stats (RPC roundtrip)
2. Calculate latency cost (pure function)
3. Inject into decision context for EV adjustment

This stage can run in:
- Paper mode: Uses mock data from fixtures
- Live mode: Makes actual RPC calls (future)
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.network_monitor import (
    NetworkMonitor,
    NetworkStats,
    calculate_latency_cost,
    LatencyParams,
    MAX_LATENCY_COST_BPS,
)
from strategy.logic import StrategyParams


logger = logging.getLogger(__name__)


@dataclass
class LatencyContext:
    """Context containing network latency metrics."""
    network_stats: NetworkStats
    latency_cost_bps: float
    is_congested: bool  # True if latency cost exceeds threshold
    can_trade: bool  # False if network is too slow
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "network_stats": self.network_stats.to_dict(),
            "latency_cost_bps": self.latency_cost_bps,
            "is_congested": self.is_congested,
            "can_trade": self.can_trade,
        }


@dataclass
class LatencyConfig:
    """Configuration for latency stage."""
    # Mode: "paper" or "live"
    mode: str = "paper"
    
    # RPC configuration (for live mode)
    rpc_endpoint: Optional[str] = None
    rpc_timeout_ms: int = 5000
    
    # Cost thresholds
    congestion_threshold_bps: float = 100.0  # Consider congested above this
    trading_block_threshold_bps: float = 500.0  # Block trading above this
    
    # Parameter overrides
    base_latency_ms: float = 200.0
    latency_cost_slope: float = 0.1
    slot_lag_penalty_bps: float = 100.0


class LatencyStage:
    """Integration stage for network latency monitoring."""
    
    def __init__(
        self,
        config: Optional[LatencyConfig] = None,
        monitor: Optional[NetworkMonitor] = None,
    ):
        """Initialize latency stage.
        
        Args:
            config: Stage configuration.
            monitor: Optional NetworkMonitor instance (created if None).
        """
        self.config = config or LatencyConfig()
        
        # Create monitor if not provided
        if monitor is None:
            monitor = NetworkMonitor(
                endpoint=self.config.rpc_endpoint,
                timeout_ms=self.config.rpc_timeout_ms,
            )
        self.monitor = monitor
        
        # Create latency params from config
        self.latency_params = LatencyParams(
            base_latency_ms=self.config.base_latency_ms,
            latency_cost_slope=self.config.latency_cost_slope,
            slot_lag_penalty_bps=self.config.slot_lag_penalty_bps,
        )
    
    def measure(self) -> LatencyContext:
        """Measure network and build latency context.
        
        In paper mode, this returns mock data.
        In live mode, this makes actual RPC calls.
        
        Returns:
            LatencyContext with network stats and cost.
        """
        if self.config.mode == "paper":
            stats = self._get_paper_stats()
        else:
            stats = self.monitor.measure()
        
        # Calculate cost (pure function)
        cost_bps = calculate_latency_cost(stats, self.latency_params)
        
        # Determine if congested
        is_congested = cost_bps >= self.config.congestion_threshold_bps
        can_trade = cost_bps < self.config.trading_block_threshold_bps
        
        context = LatencyContext(
            network_stats=stats,
            latency_cost_bps=cost_bps,
            is_congested=is_congested,
            can_trade=can_trade,
        )
        
        logger.debug(f"Latency context: {cost_bps:.1f} bps, congested={is_congested}, can_trade={can_trade}")
        
        return context
    
    def _get_paper_stats(self) -> NetworkStats:
        """Get mock network stats for paper mode.
        
        Returns realistic simulated values for testing.
        """
        import random
        
        # Simulate occasional congestion
        if random.random() < 0.1:
            # Congested: 500-1000ms
            return NetworkStats(
                rpc_roundtrip_ms=random.uniform(500, 1000),
                slot_lag_ms=None,
                measured_at=0,
                is_estimated=True,
            )
        elif random.random() < 0.05:
            # Outage: timeout
            return NetworkStats(
                rpc_roundtrip_ms=5000,
                slot_lag_ms=None,
                measured_at=0,
                is_estimated=True,
            )
        else:
            # Normal: 150-250ms
            return NetworkStats(
                rpc_roundtrip_ms=random.uniform(150, 250),
                slot_lag_ms=None,
                measured_at=0,
                is_estimated=True,
            )
    
    def adjust_ev(self, base_ev: float, context: LatencyContext) -> float:
        """Adjust EV by subtracting latency cost.
        
        Args:
            base_ev: Base expected value.
            context: Latency context with cost.
        
        Returns:
            Adjusted EV (base - latency_cost).
        """
        # Convert bps to decimal and subtract from EV
        latency_decimal = context.latency_cost_bps / 10000.0
        return max(0.0, base_ev - latency_decimal)


def load_scenario(fixture_path: str | Path) -> Dict[str, Any]:
    """Load a latency scenario from fixture."""
    path = Path(fixture_path)
    with open(path, "r") as f:
        return json.load(f)


def run_paper_test(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Run a paper mode test with given scenario.
    
    Args:
        Scenario dict with:
        - description: Test description
        - rpc_roundtrip_ms: Simulated RPC latency
        - slot_lag_ms: Optional slot lag
        - params: LatencyParams values
        - expected_cost: Expected cost in bps
    """
    # Create stats from scenario
    stats = NetworkStats(
        rpc_roundtrip_ms=scenario["rpc_roundtrip_ms"],
        slot_lag_ms=scenario.get("slot_lag_ms"),
        measured_at=0,
        is_estimated=scenario.get("is_estimated", False),
    )
    
    # Create params from scenario
    params = LatencyParams(
        base_latency_ms=scenario.get("base_latency_ms", 200.0),
        latency_cost_slope=scenario.get("latency_cost_slope", 0.1),
        slot_lag_penalty_bps=scenario.get("slot_lag_penalty_bps", 100.0),
    )
    
    # Calculate cost
    cost = calculate_latency_cost(stats, params)
    
    return {
        "description": scenario.get("description", "unknown"),
        "rpc_roundtrip_ms": stats.rpc_roundtrip_ms,
        "calculated_cost_bps": cost,
        "expected_cost_bps": scenario.get("expected_cost_bps", 0.0),
        "passed": abs(cost - scenario.get("expected_cost_bps", 0.0)) < 0.1,
    }


# Example usage and self-test
if __name__ == "__main__":
    import random
    
    print("=== Latency Stage Self-Test ===\n")
    
    # Test scenarios
    scenarios = [
        {
            "description": "Fast Network",
            "rpc_roundtrip_ms": 150.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "expected_cost_bps": 0.0,
        },
        {
            "description": "Normal Network",
            "rpc_roundtrip_ms": 200.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "expected_cost_bps": 0.0,
        },
        {
            "description": "Slow Network",
            "rpc_roundtrip_ms": 500.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "expected_cost_bps": 30.0,
        },
        {
            "description": "Congested Network",
            "rpc_roundtrip_ms": 1000.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "expected_cost_bps": 80.0,
        },
        {
            "description": "Outage (Timeout)",
            "rpc_roundtrip_ms": 5000.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "expected_cost_bps": 1000.0,  # Capped at MAX_LATENCY_COST_BPS
        },
        {
            "description": "With Slot Lag Penalty",
            "rpc_roundtrip_ms": 300.0,
            "slot_lag_ms": 3000.0,
            "base_latency_ms": 200.0,
            "latency_cost_slope": 0.1,
            "slot_lag_penalty_bps": 100.0,
            "expected_cost_bps": 110.0,  # (300-200)*0.1 + 100
        },
    ]
    
    print("Running Test Scenarios:")
    all_passed = True
    for scenario in scenarios:
        result = run_paper_test(scenario)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {result['description']}: cost={result['calculated_cost_bps']:.1f} bps [{status}]")
        if not result["passed"]:
            all_passed = False
            print(f"    Expected: {result['expected_cost_bps']:.1f}")
    
    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed!'}")
    
    print("\nEV Adjustment Example:")
    stage = LatencyStage()
    context = stage.measure()
    base_ev = 0.05  # 5% base EV
    adjusted_ev = stage.adjust_ev(base_ev, context)
    print(f"  Base EV: {base_ev:.2%}")
    print(f"  Latency Cost: {context.latency_cost_bps:.1f} bps ({context.latency_cost_bps/100:.2f}%)")
    print(f"  Adjusted EV: {adjusted_ev:.2%}")
    print(f"  Can Trade: {context.can_trade}")
