#!/usr/bin/env python3
"""
Distributed Backtest Harness CLI.

Orchestrates parallel backtests across multiple CPU cores.
1. Generates parameter grid from config.
2. Distributes tasks to worker processes.
3. Aggregates results and selects best configuration.

Usage:
    python -m integration.parallel_backtest \
        --grid <yaml> --trades <jsonl> --workers <int> --out <json>

Output:
    optimization_results.v1.json
"""

import argparse
import json
import yaml
import sys
import os
import time
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.optimization.grid_gen import generate_grid, select_best


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def run_backtest_task(config: Dict[str, Any], trades_path: str) -> Dict[str, Any]:
    """
    Worker function to run a single backtest simulation.
    
    In a real scenario, this would import and run the full backtest pipeline.
    For this harness implementation, we simulate execution with a lightweight model
    that produces deterministic results based on parameters.
    
    Args:
        config: Parameter configuration dict
        trades_path: Path to trades file (unused in simulation but part of interface)
        
    Returns:
        Result dict including params and metrics
    """
    # Simulate processing time (ms)
    # time.sleep(0.01) 
    
    # Extract params
    tp = config.get("tp_pct", 0.05)
    sl = config.get("sl_pct", -0.05)
    
    # Simulate metric calculation (deterministic formula for testing)
    # Higher TP is better, tighter SL is worse (just a mock relationship)
    sharpe = (tp * 100) - (abs(sl) * 50)
    roi_total = sharpe * 0.1
    
    return {
        "params": config,
        "metrics": {
            "sharpe": round(sharpe, 4),
            "roi_total": round(roi_total, 4),
            "trades_count": 100
        },
        "status": "completed"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Distributed Backtest Harness: Parallel Grid Search"
    )
    parser.add_argument(
        "--grid",
        type=str,
        required=True,
        help="Path to grid config YAML"
    )
    parser.add_argument(
        "--trades",
        type=str,
        required=True,
        help="Path to historical trades JSONL"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count(),
        help="Number of parallel workers"
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr"
    )
    
    args = parser.parse_args()
    
    # Load grid config
    grid_path = Path(args.grid)
    if not grid_path.exists():
        print(f"Error: Grid file not found: {grid_path}", file=sys.stderr)
        sys.exit(1)
        
    param_ranges = load_yaml(grid_path)
    grid = generate_grid(param_ranges)
    
    if args.verbose:
        print(f"Generated {len(grid)} configurations to test", file=sys.stderr)
        print(f"Starting execution with {args.workers} workers...", file=sys.stderr)
        
    start_time = time.time()
    results = []
    
    # Parallel Execution
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {executor.submit(run_backtest_task, config, args.trades): config for config in grid}
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                print(f"Worker exception: {e}", file=sys.stderr)
                
    elapsed = time.time() - start_time
    
    if args.verbose:
        print(f"Completed {len(results)} backtests in {elapsed:.2f}s", file=sys.stderr)
        
    # Select best
    best_result, best_val = select_best(results, metric="sharpe")
    
    # Output structure
    output = {
        "version": "optimization_results.v1",
        "timestamp": int(time.time()),
        "total_configs": len(grid),
        "successful_runs": len(results),
        "best_result": best_result,
        "elapsed_sec": round(elapsed, 2),
        "all_results": results
    }
    
    # Write to file
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
        
    if args.verbose:
        print(f"Wrote results to {out_path}", file=sys.stderr)
        if best_result:
            print(f"Best Config (Sharpe {best_val}): {best_result['params']}", file=sys.stderr)
            
    # Print JSON summary to stdout
    print(json.dumps({
        "status": "success",
        "total": len(results),
        "elapsed": round(elapsed, 2),
        "best_metric": best_val
    }))


if __name__ == "__main__":
    main()
