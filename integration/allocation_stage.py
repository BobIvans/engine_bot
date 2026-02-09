"""
integration/allocation_stage.py

Glue stage for dynamic mode allocation.

PR-V.3
"""
import sys
import json
from typing import Dict, Optional, Any

import yaml

from strategy.allocation import (
    ModeAllocator,
    AllocationConfig,
    AllocationResult,
)


class AllocationContext:
    """Context for allocation stage."""
    
    def __init__(self):
        self.total_equity_usd: float = 0.0
        self.volatility_score: float = 0.0
        self.regime_score: float = 0.0
        self.allocation_result: Optional[AllocationResult] = None
        self.config: Optional[AllocationConfig] = None


def load_config(config_file: str) -> AllocationConfig:
    """Load allocation configuration from YAML."""
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)
    
    weights = data.get('weights', {})
    params = data.get('params', {})
    
    return AllocationConfig(
        base_weights=weights,
        vol_sensitivity=params.get('vol_sensitivity', 0.5),
        regime_sensitivity=params.get('regime_sensitivity', 0.5),
        min_weight=params.get('min_weight', 0.0),
        cash_buffer_bearish=params.get('cash_buffer_bearish', 0.5),
        risk_on_modes=params.get('risk_on_modes', ['U', 'S']),
        risk_off_modes=params.get('risk_off_modes', ['M', 'L', 'C']),
    )


def run_allocation_stage(
    equity_usd: float,
    volatility: float,
    regime: float,
    config: AllocationConfig,
    dump_json: bool = False,
) -> AllocationResult:
    """
    Run the allocation stage.
    
    Args:
        equity_usd: Total equity in USD
        volatility: Volatility score (0-1)
        regime: Regime score (-1 to 1)
        config: Allocation configuration
        dump_json: If True, output JSON to stdout
        
    Returns:
        AllocationResult
    """
    allocator = ModeAllocator(config)
    result = allocator.compute_allocation(equity_usd, volatility, regime)
    
    if dump_json:
        print(json.dumps(result.to_dict()))
    
    return result


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Allocation Stage')
    parser.add_argument('--config', '-c', required=True, help='Config YAML file')
    parser.add_argument('--equity', '-e', type=float, required=True, help='Total equity USD')
    parser.add_argument('--volatility', '-v', type=float, required=True, help='Volatility score (0-1)')
    parser.add_argument('--regime', '-r', type=float, required=True, help='Regime score (-1 to 1)')
    parser.add_argument('--dump', action='store_true', help='Dump JSON to stdout')
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    result = run_allocation_stage(
        args.equity,
        args.volatility,
        args.regime,
        config,
        dump_json=args.dump,
    )
    
    # Print summary to stderr
    print(f"[allocation_stage] Equity: ${args.equity:.2f}", file=sys.stderr)
    print(f"[allocation_stage] Vol: {args.volatility:.2f}, Regime: {args.regime:.2f}", file=sys.stderr)
    print(f"[allocation_stage] Allocations: {result.allocations}", file=sys.stderr)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
