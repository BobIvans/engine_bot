"""
Pure logic for Grid Search Optimization.

Generates parameter combinations (Cartesian Product) for parallel backtesting
and selects the best configuration based on performance metrics.
"""

import itertools
from typing import Dict, List, Any, Optional, Tuple


def generate_grid(param_ranges: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Generate all combinations of parameters from provided ranges.
    
    Args:
        param_ranges: Dict mapping parameter names to lists of values
                      e.g. {"tp": [0.05, 0.1], "sl": [-0.05]}
                      
    Returns:
        List of configuration dictionaries (Cartesian Product)
    """
    if not param_ranges:
        return []
        
    # Extract keys and value lists in consistent order
    keys = sorted(param_ranges.keys())
    value_lists = [param_ranges[k] for k in keys]
    
    # Generate cartesian product
    combinations = list(itertools.product(*value_lists))
    
    # Reconstruct dicts
    grid = []
    for combo in combinations:
        config = {k: v for k, v in zip(keys, combo)}
        grid.append(config)
        
    return grid


def select_best(
    results: List[Dict[str, Any]], 
    metric: str = "sharpe"
) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Select the best result from a list of backtest results.
    
    Args:
        results: List of result dicts, each containing 'params' and 'metrics'
        metric: Metric name to maximize (e.g. 'sharpe', 'roi_total')
        
    Returns:
        Tuple of (best_result_dict, best_metric_value)
    """
    if not results:
        return None, -float("inf")
        
    best_result = None
    best_value = -float("inf")
    
    for res in results:
        metrics = res.get("metrics", {})
        value = metrics.get(metric, -float("inf"))
        
        # Handle None or non-numeric values gracefully
        if not isinstance(value, (int, float)):
            continue
            
        if value > best_value:
            best_value = value
            best_result = res
            
    return best_result, best_value


if __name__ == "__main__":
    # Quick test
    ranges = {
        "tp_pct": [0.05, 0.10],
        "sl_pct": [-0.05, -0.02]
    }
    grid = generate_grid(ranges)
    print(f"Generated {len(grid)} configs:")
    for c in grid:
        print(c)
