"""
strategy/optimization/grid.py

Parameter grid generator for strategy optimization.

Generates deterministic combinations of parameters using itertools.product.

PR-V.2
"""
import sys
from typing import Dict, List, Any, Iterator


class ParameterGrid:
    """
    Generates all combinations of parameters from a configuration dictionary.
    
    Uses itertools.product for deterministic grid generation.
    
    PR-V.2
    """
    
    def __init__(self):
        """Initialize the parameter grid generator."""
        pass
    
    def generate(self, param_ranges: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """
        Generate all combinations of parameters.
        
        Args:
            param_ranges: Dictionary where keys are parameter names
                         and values are lists of possible values.
                         Example: {"stop_loss": [-0.05, -0.1], "tp": [0.05, 0.1]}
        
        Returns:
            List of parameter dictionaries, each representing one combination.
            Order is deterministic (sorted by parameter name, then by value).
        """
        if not param_ranges:
            print("[grid] WARNING: Empty parameter ranges", file=sys.stderr)
            return []
        
        # Sort parameter names for determinism
        sorted_param_names = sorted(param_ranges.keys())
        
        # Create list of value lists in sorted order
        value_lists = [param_ranges[name] for name in sorted_param_names]
        
        # Generate all combinations using itertools.product
        from itertools import product
        combinations = list(product(*value_lists))
        
        # Convert to list of dictionaries
        result = []
        for combo in combinations:
            config = {}
            for i, name in enumerate(sorted_param_names):
                config[name] = combo[i]
            result.append(config)
        
        print(f"[grid] Generated {len(result)} parameter combinations", file=sys.stderr)
        
        return result
    
    def generate_from_step(
        self,
        param_ranges: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate parameter grid from ranges with step values.
        
        Args:
            param_ranges: Dictionary where keys are parameter names and values
                         are dicts with 'min', 'max', 'step'.
                         Example: {"stop_loss": {"min": -0.1, "max": -0.02, "step": 0.01}}
        
        Returns:
            List of parameter dictionaries.
        """
        expanded = {}
        
        for param_name, range_config in param_ranges.items():
            values = []
            current = range_config['min']
            step = range_config['step']
            max_val = range_config['max']
            
            # Handle positive and negative step directions
            if step > 0:
                while current <= max_val + 1e-9:  # Tolerance for floating point
                    values.append(round(current, 4))
                    current += step
            else:
                while current >= max_val - 1e-9:
                    values.append(round(current, 4))
                    current += step
            
            expanded[param_name] = values
        
        return self.generate(expanded)
    
    def count_combinations(self, param_ranges: Dict[str, List[Any]]) -> int:
        """
        Count total number of combinations without generating them.
        
        Useful for estimating computation time.
        
        Args:
            param_ranges: Parameter ranges dictionary
            
        Returns:
            Total number of combinations
        """
        count = 1
        for values in param_ranges.values():
            count *= len(values)
        return count
