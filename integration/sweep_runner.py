"""
integration/sweep_runner.py

CLI orchestrator for parameter sweep optimization.

Load Data -> Grid Loop -> Rank -> Dump leaderboard.

PR-V.2
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml

from strategy.optimization.grid import ParameterGrid
from strategy.optimization.ranking import (
    calculate_metrics,
    rank_configs,
    get_best_config,
    SweepResult,
)


def load_trades(trades_file: str) -> List[Dict]:
    """Load trades from JSONL file."""
    trades = []
    with open(trades_file, 'r') as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
    
    print(f"[sweep_runner] Loaded {len(trades)} trades", file=sys.stderr)
    return trades


def load_config(config_file: str) -> Dict:
    """Load sweep configuration from YAML."""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    print(f"[sweep_runner] Loaded config from {config_file}", file=sys.stderr)
    return config


def simulate_with_params(trades: List[Dict], params: Dict[str, Any]) -> List[Dict]:
    """
    Simulate trades with given parameters.
    
    This is a simplified simulation that applies filters based on params.
    In a real scenario, this would execute the full strategy logic.
    
    Args:
        trades: List of trades
        params: Strategy parameters (stop_loss, take_profit, etc.)
        
    Returns:
        Filtered list of trades
    """
    filtered = []
    
    # Extract parameters with defaults
    min_hold = params.get('min_hold_seconds', 0)
    max_hold = params.get('max_hold_seconds', float('inf'))
    min_pnl = params.get('min_pnl_pct', -float('inf'))
    max_pnl = params.get('max_pnl_pct', float('inf'))
    
    for trade in trades:
        # Apply filters
        hold_time = trade.get('hold_seconds', 0)
        pnl = trade.get('pnl_pct', 0)
        
        if hold_time < min_hold:
            continue
        if hold_time > max_hold:
            continue
        if pnl < min_pnl:
            continue
        if pnl > max_pnl:
            continue
        
        filtered.append(trade)
    
    return filtered


def run_sweep(
    trades: List[Dict],
    param_ranges: Dict[str, List[Any]],
    verbose: bool = True,
) -> List[SweepResult]:
    """
    Run parameter sweep on trades.
    
    Args:
        trades: List of trades
        param_ranges: Parameter ranges to sweep
        verbose: Print progress
        
    Returns:
        List of SweepResult objects
    """
    grid = ParameterGrid()
    param_combinations = grid.generate(param_ranges)
    
    if verbose:
        print(f"[sweep_runner] Grid size: {len(param_combinations)} configs", file=sys.stderr)
    
    results = []
    start_time = time.time()
    
    for i, params in enumerate(param_combinations):
        # Simulate with these parameters
        filtered_trades = simulate_with_params(trades, params)
        
        # Calculate metrics
        metrics = calculate_metrics(filtered_trades)
        
        # Create result
        result = SweepResult(
            params=params,
            metrics=metrics,
        )
        results.append(result)
        
        if verbose and (i + 1) % 10 == 0:
            elapsed = time.time() - start_time
            print(f"[sweep_runner] Progress: {i + 1}/{len(param_combinations)} ({elapsed:.1f}s)", file=sys.stderr)
    
    elapsed = time.time() - start_time
    if verbose:
        print(f"[sweep_runner] Completed {len(results)} configs in {elapsed:.2f}s", file=sys.stderr)
    
    return results


def save_leaderboard(
    results: List[SweepResult],
    output_file: str,
    top_n: int = 10,
):
    """
    Save leaderboard to JSON file.
    
    Args:
        results: List of SweepResult objects
        output_file: Path to output JSON file
        top_n: Number of top results to save
    """
    # Rank and get best
    ranked = rank_configs(results, sort_by='sharpe_ratio', top_n=top_n)
    best = get_best_config(results)
    
    # Build output structure
    # leaderboard.v1 format for backward compatibility
    leaderboard = {
        "version": "v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_configs": len(results),
        "best_config": best,
        "ranking": [
            {
                "rank": i + 1,
                "params": r.params,
                "metrics": r.metrics,
            }
            for i, r in enumerate(ranked)
        ],
    }
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(leaderboard, f, indent=2)
    
    print(f"[sweep_runner] Saved leaderboard to {output_file}", file=sys.stderr)


def main():
    """Main entry point for CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Strategy Parameter Sweep')
    parser.add_argument('--config', '-c', required=True, help='Sweep config YAML')
    parser.add_argument('--trades', '-t', required=True, help='Trades JSONL file')
    parser.add_argument('--output', '-o', default='leaderboard.json', help='Output file')
    parser.add_argument('--top', '-n', type=int, default=10, help='Top N results')
    
    args = parser.parse_args()
    
    # Load data
    trades = load_trades(args.trades)
    config = load_config(args.config)
    
    # Get parameter ranges from config
    param_ranges = config.get('parameters', {})
    
    if not param_ranges:
        print("[sweep_runner] ERROR: No parameters defined in config", file=sys.stderr)
        sys.exit(1)
    
    # Run sweep
    results = run_sweep(trades, param_ranges)
    
    # Save leaderboard
    save_leaderboard(results, args.output, top_n=args.top)
    
    # Print summary
    best = get_best_config(results)
    if best:
        print(f"[sweep_runner] Best config: Sharpe={best['metrics'].get('sharpe_ratio', 0):.2f}, "
              f"ROI={best['metrics'].get('total_roi', 0):.2f}%", file=sys.stderr)


if __name__ == '__main__':
    main()
