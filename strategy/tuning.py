"""strategy/tuning.py

PR-E.4 Parameter Tuning Harness - Pure logic for parameter space generation.

Functions:
- generate_configs: Generate config variations based on ranges (Grid or Random search)
- _set_nested: Set a value in a nested dict using dot notation
- _get_nested: Get a value from a nested dict using dot notation

Design goals:
- Pure logic (stateless)
- Deterministic output for random search with seed
- Support dot-notation keys (e.g., modes.U.tp_pct)
"""

from typing import Any, Dict, Iterator, List, Union


ParamValue = Union[int, float, str, bool]


def _set_nested(d: Dict[str, Any], key: str, value: ParamValue) -> Dict[str, Any]:
    """Set a value in a nested dict using dot notation.

    Args:
        d: The dict to modify.
        key: Dot-notation key (e.g., "modes.U.tp_pct").
        value: Value to set.

    Returns:
        The modified dict.
    """
    parts = key.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return d


def _get_nested(d: Dict[str, Any], key: str) -> Any:
    """Get a value from a nested dict using dot notation.

    Args:
        d: The dict to read from.
        key: Dot-notation key (e.g., "modes.U.tp_pct").

    Returns:
        The value at the key path, or None if not found.
    """
    parts = key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def generate_param_grid(
    base_config: Dict[str, Any],
    ranges: Dict[str, List[ParamValue]],
    method: str = "grid",
    samples: int = 10,
    seed: int = 42,
) -> Iterator[Dict[str, Any]]:
    """Generate config variations based on defined ranges.

    Args:
        base_config: Base strategy configuration dict.
        ranges: Dict mapping dot-notation keys to lists of values.
                Example: {"modes.U.tp_pct": [0.01, 0.05, 0.10]}
        method: "grid" for full grid search, "random" for random sampling.
        samples: Number of samples for random search.
        seed: Random seed for reproducibility.

    Yields:
        Config dict with overridden parameters.
    """
    import random

    # Set seed for deterministic random sampling
    random.seed(seed)

    # Extract all parameter keys and their value lists
    param_keys = list(ranges.keys())
    value_lists = [ranges[k] for k in param_keys]

    if method == "grid":
        # Cartesian product of all value combinations
        def cartesian_product(lists: List[List[Any]]) -> Iterator[List[Any]]:
            if not lists:
                yield []
                return
            for head in lists[0]:
                for tail in cartesian_product(lists[1:]):
                    yield [head] + tail

        for combination in cartesian_product(value_lists):
            config = base_config.copy()
            for key, value in zip(param_keys, combination):
                _set_nested(config, key, value)
            yield config

    elif method == "random":
        # Random sampling from each value list
        for _ in range(samples):
            config = base_config.copy()
            for key, values in zip(param_keys, value_lists):
                value = random.choice(values)
                _set_nested(config, key, value)
            yield config

    else:
        raise ValueError(f"Unknown method: {method}. Use 'grid' or 'random'.")


def generate_random_search(
    base_config: Dict[str, Any],
    ranges: Dict[str, List[ParamValue]],
    samples: int = 10,
    seed: int = 42,
) -> Iterator[Dict[str, Any]]:
    """Generate random parameter combinations from ranges.

    This is an alias for generate_configs with method='random'.

    Args:
        base_config: Base strategy configuration dict.
        ranges: Dict mapping dot-notation keys to lists of values.
        samples: Number of samples to generate.
        seed: Random seed for reproducibility.

    Yields:
        Config dict with randomly sampled parameters.
    """
    return generate_param_grid(
        base_config=base_config,
        ranges=ranges,
        method="random",
        samples=samples,
        seed=seed,
    )


def extract_params_for_result(config: Dict[str, Any], ranges: Dict[str, List[ParamValue]]) -> Dict[str, Any]:
    """Extract the overridden parameters from a config for result logging.

    Args:
        config: The config dict with potential overrides.
        ranges: The original ranges dict (keys define what was tunable).

    Returns:
        Dict mapping original keys to their values in the config.
    """
    result = {}
    for key in ranges.keys():
        value = _get_nested(config, key)
        if value is not None:
            result[key] = value
    return result
