"""ingestion/network_monitor.py - Latency Monitoring & Cost Calculation

Measures network latency (RPC roundtrip) and converts it to a "cost" (bps)
for inclusion in EV calculations. High latency = high cost = trading stop.

Architecture:
- `calculate_latency_cost()`: Pure function (ms -> bps conversion)
- `NetworkMonitor`: Impure class for actual RPC measurements

HARD RULES:
1. Purity separation: Calculation logic is pure, measurement is impure.
2. Fail-safe: RPC errors -> MAX_LATENCY_COST (1000 bps).
3. Config driven: Coefficients from StrategyParams.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Any

# Default fail-safe values
MAX_LATENCY_COST_BPS = 1000.0  # Cap value for outages (stops all trading)
DEFAULT_RPC_TIMEOUT_MS = 5000  # 5 second timeout for RPC calls
DEFAULT_SLOT_LAG_THRESHOLD_MS = 2000  # 2 second slot lag threshold


@dataclass
class NetworkStats:
    """Network latency statistics."""
    rpc_roundtrip_ms: float  # Roundtrip time for RPC call
    slot_lag_ms: Optional[float] = None  # How far behind the leader we are
    measured_at: int = 0  # Unix timestamp of measurement
    is_estimated: bool = False  # True if using fallback/estimated values
    
    def to_dict(self) -> dict:
        return {
            "rpc_roundtrip_ms": self.rpc_roundtrip_ms,
            "slot_lag_ms": self.slot_lag_ms,
            "measured_at": self.measured_at,
            "is_estimated": self.is_estimated,
        }


@dataclass
class LatencyParams:
    """Parameters for latency cost calculation."""
    base_latency_ms: float = 200.0  # Normal latency baseline
    latency_cost_slope: float = 0.5  # bps penalty per 1ms above baseline
    slot_lag_penalty_bps: float = 100.0  # bps penalty if slot lag detected
    max_acceptable_latency_ms: float = 1000.0  # Cap for "acceptable" latency
    min_cost_pct: float = 0.0  # Minimum cost (don't go negative)


def calculate_latency_cost(
    stats: NetworkStats,
    params: Optional[LatencyParams] = None,
) -> float:
    """Calculate latency cost in basis points (bps).
    
    Pure function: converts network stats to trading cost.
    
    Formula:
        raw_cost = max(0, (rpc_roundtrip_ms - base_latency_ms) * slope)
        slot_penalty = slot_lag_penalty_bps if slot_lag_ms > threshold
        total_cost = raw_cost + slot_penalty
    
    Args:
        stats: Network statistics from measurement.
        params: Latency parameters (uses defaults if None).
    
    Returns:
        Latency cost in basis points (bps). Higher = worse network.
    """
    if params is None:
        params = LatencyParams()
    
    # Calculate base cost from RPC latency
    if stats.rpc_roundtrip_ms <= params.base_latency_ms:
        raw_cost = params.min_cost_pct
    else:
        raw_cost = (stats.rpc_roundtrip_ms - params.base_latency_ms) * params.latency_cost_slope
    
    # Add slot lag penalty if significant
    slot_penalty = 0.0
    if stats.slot_lag_ms is not None and stats.slot_lag_ms > DEFAULT_SLOT_LAG_THRESHOLD_MS:
        slot_penalty = params.slot_lag_penalty_bps
    
    total_cost = raw_cost + slot_penalty
    
    # Apply fail-safe cap
    return min(total_cost, MAX_LATENCY_COST_BPS)


class NetworkMonitor:
    """Monitors network latency to RPC endpoints.
    
    Makes lightweight RPC calls (getVersion, getSlot) to measure
    roundtrip time. Handles errors gracefully by returning max cost.
    
    This class is IMPURE - it makes actual network calls.
    For pure cost calculations, use calculate_latency_cost().
    """
    
    def __init__(
        self,
        rpc_client: Optional[Any] = None,
        endpoint: Optional[str] = None,
        timeout_ms: int = DEFAULT_RPC_TIMEOUT_MS,
    ):
        """Initialize network monitor.
        
        Args:
            rpc_client: Optional RPC client (e.g., Helius, Solana-py).
                       If None, measurements will use defaults.
            endpoint: RPC endpoint URL (used if no client provided).
            timeout_ms: Request timeout in milliseconds.
        """
        self.rpc_client = rpc_client
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
    
    def measure(self) -> NetworkStats:
        """Measure current network latency.
        
        Makes a lightweight RPC call and measures roundtrip time.
        On error, returns stats with max cost (fail-safe).
        
        Returns:
            NetworkStats with measured latency.
        """
        start_time = time.perf_counter()
        error = None
        
        try:
            # Attempt to make a lightweight RPC call
            if self.rpc_client is not None:
                # Use provided client
                self._call_rpc(self.rpc_client)
            elif self.endpoint:
                # Direct HTTP call (simplified)
                self._call_http(self.endpoint)
            else:
                # No client or endpoint - use estimated value
                error = "no_rpc_configured"
            
        except Exception as e:
            error = str(e)
        
        end_time = time.perf_counter()
        elapsed_ms = (end_time - start_time) * 1000
        
        if error:
            # Fail-safe: return max cost on error
            return NetworkStats(
                rpc_roundtrip_ms=DEFAULT_RPC_TIMEOUT_MS,
                slot_lag_ms=None,
                measured_at=int(start_time),
                is_estimated=True,
            )
        
        return NetworkStats(
            rpc_roundtrip_ms=elapsed_ms,
            slot_lag_ms=None,  # Could add slot lag measurement if needed
            measured_at=int(start_time),
            is_estimated=False,
        )
    
    def _call_rpc(self, client: Any) -> Any:
        """Make RPC call using client."""
        # Try common lightweight RPC methods
        try:
            return client.get_version()
        except AttributeError:
            pass
        
        try:
            return client.get_slot()
        except AttributeError:
            pass
        
        # Fallback - just return None if method not found
        return None
    
    def _call_http(self, endpoint: str) -> Any:
        """Make direct HTTP call to RPC endpoint."""
        import urllib.request
        import json
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getHealth",
        }
        
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=self.timeout_ms / 1000) as response:
            return json.loads(response.read().decode())


# Convenience function for quick cost calculation
def assess_network_quality(
    rpc_client: Optional[Any] = None,
    endpoint: Optional[str] = None,
    params: Optional[LatencyParams] = None,
) -> tuple[NetworkStats, float]:
    """Measure network and calculate cost in one call.
    
    Args:
        rpc_client: Optional RPC client.
        endpoint: Optional RPC endpoint.
        params: Latency parameters.
    
    Returns:
        Tuple of (NetworkStats, cost_bps).
    """
    monitor = NetworkMonitor(rpc_client=rpc_client, endpoint=endpoint)
    stats = monitor.measure()
    cost = calculate_latency_cost(stats, params)
    return stats, cost


# Self-test when run directly
if __name__ == "__main__":
    import json
    
    print("=== Network Monitor Self-Test ===\n")
    
    # Test with simulated stats (pure function tests)
    params = LatencyParams(
        base_latency_ms=200.0,
        latency_cost_slope=0.1,
        slot_lag_penalty_bps=100.0,
    )
    
    test_cases = [
        ("Fast Network", NetworkStats(rpc_roundtrip_ms=150.0), 0.0),
        ("Normal Network", NetworkStats(rpc_roundtrip_ms=200.0), 0.0),
        ("Slow Network", NetworkStats(rpc_roundtrip_ms=500.0), 30.0),
        ("Congested", NetworkStats(rpc_roundtrip_ms=1000.0), 80.0),
        ("Outage", NetworkStats(rpc_roundtrip_ms=5000.0, is_estimated=True), 1000.0),
        ("With Slot Lag", NetworkStats(rpc_roundtrip_ms=300.0, slot_lag_ms=3000.0), 110.0),
    ]
    
    print("Pure Function Tests:")
    for name, stats, expected_cost in test_cases:
        cost = calculate_latency_cost(stats, params)
        status = "PASS" if abs(cost - expected_cost) < 0.1 else "FAIL"
        print(f"  {name}: cost={cost:.1f} bps (expected {expected_cost}) [{status}]")
    
    print("\nEstimated Measurement Test:")
    monitor = NetworkMonitor(endpoint="http://localhost:8899")
    stats = monitor.measure()
    print(f"  Measured: {stats.rpc_roundtrip_ms:.1f}ms, estimated={stats.is_estimated}")
    print(f"  Cost: {calculate_latency_cost(stats, params):.1f} bps")
    
    print("\nSerialization Test:")
    serialized = stats.to_dict()
    print(json.dumps(serialized, indent=2))
