# strategy/statistics.py
# Pure logic for bootstrap statistics and confidence intervals.
# No I/O side effects.

from typing import Dict, List, Iterable, Optional


def calculate_quantiles(
    values: Iterable[float],
    percentiles: List[int] = None,
    interpolation: str = "linear",
) -> Dict[str, float]:
    """
    Calculate quantiles for the given values.

    Args:
        values: Iterable of numeric values.
        percentiles: List of percentile values to compute (e.g., [5, 50, 95]).
        interpolation: Interpolation method for discrete data.
                       Options: 'linear', 'lower', 'higher', 'midpoint', 'nearest'.

    Returns:
        Dict mapping percentile to value (e.g., {"p05": ..., "p50": ..., "p95": ...}).
    """
    if percentiles is None:
        percentiles = [5, 50, 95]

    # Convert to sorted list for quantile calculation
    sorted_values = sorted(values)
    n = len(sorted_values)

    if n == 0:
        raise ValueError("Cannot calculate quantiles of empty values")

    result = {}
    for p in percentiles:
        if p < 0 or p > 100:
            raise ValueError(f"Percentile {p} out of range [0, 100]")

        # Calculate index using linear interpolation
        idx = (p / 100.0) * (n - 1)

        lower_idx = int(idx)
        upper_idx = lower_idx + 1

        if upper_idx >= n:
            # At or beyond last element
            result[f"p{p}"] = sorted_values[-1]
        else:
            # Interpolate between lower_idx and upper_idx
            frac = idx - lower_idx
            if interpolation == "linear":
                result[f"p{p}"] = sorted_values[lower_idx] + frac * (
                    sorted_values[upper_idx] - sorted_values[lower_idx]
                )
            elif interpolation == "lower":
                result[f"p{p}"] = sorted_values[lower_idx]
            elif interpolation == "higher":
                result[f"p{p}"] = sorted_values[upper_idx]
            elif interpolation == "midpoint":
                result[f"p{p}"] = (sorted_values[lower_idx] + sorted_values[upper_idx]) / 2
            elif interpolation == "nearest":
                if frac < 0.5:
                    result[f"p{p}"] = sorted_values[lower_idx]
                else:
                    result[f"p{p}"] = sorted_values[upper_idx]
            else:
                # Default to linear
                result[f"p{p}"] = sorted_values[lower_idx] + frac * (
                    sorted_values[upper_idx] - sorted_values[lower_idx]
                )

    return result


def calculate_win_probability(pnl_values: List[float], threshold: float = 0.0) -> float:
    """
    Calculate the fraction of runs where PnL exceeds a threshold.

    Args:
        pnl_values: List of PnL values from each simulation run.
        threshold: Threshold for "win" (default: 0.0).

    Returns:
        Fraction of runs where PnL > threshold, as a float in [0, 1].
    """
    if not pnl_values:
        raise ValueError("Cannot calculate win probability of empty values")

    wins = sum(1 for pnl in pnl_values if pnl > threshold)
    return wins / len(pnl_values)


def calculate_max_drawdown(values: List[float]) -> float:
    """
    Calculate the maximum drawdown from a series of cumulative values.

    Args:
        values: List of cumulative values (e.g., portfolio values or cumulative PnL).

    Returns:
        Maximum drawdown as a positive value (e.g., 0.15 for 15% drawdown).
    """
    if not values:
        raise ValueError("Cannot calculate max drawdown of empty values")

    max_drawdown = 0.0
    peak = values[0]

    for value in values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak != 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return max_drawdown


def calculate_statistics(
    pnl_values: List[float],
    drawdown_values: List[float],
    roi_percentiles: List[int] = None,
    dd_percentiles: List[int] = None,
) -> Dict:
    """
    Calculate comprehensive statistics for Monte Carlo results.

    Args:
        pnl_values: List of PnL values from each run.
        drawdown_values: List of max drawdown values from each run.
        roi_percentiles: Percentiles for ROI (default: [5, 50, 95]).
        dd_percentiles: Percentiles for max drawdown (default: [5, 50, 95]).

    Returns:
        Dict with roi_pct, max_dd_pct, and win_prob.
    """
    if roi_percentiles is None:
        roi_percentiles = [5, 50, 95]
    if dd_percentiles is None:
        dd_percentiles = [5, 50, 95]

    roi_quantiles = calculate_quantiles(pnl_values, roi_percentiles)
    dd_quantiles = calculate_quantiles(drawdown_values, dd_percentiles)
    win_prob = calculate_win_probability(pnl_values)

    return {
        "roi_pct": {k: round(v, 4) for k, v in roi_quantiles.items()},
        "max_dd_pct": {k: round(v, 4) for k, v in dd_quantiles.items()},
        "win_prob": round(win_prob, 4),
    }


def bootstrap_confidence_interval(
    values: List[float],
    statistic: str = "mean",
    confidence: float = 0.95,
    n_bootstrap: int = 10000,
    random_seed: Optional[int] = None,
) -> Dict[str, float]:
    """
    Calculate confidence interval using bootstrap resampling.

    Args:
        values: Original sample values.
        statistic: Statistic to bootstrap ("mean", "median", "std").
        confidence: Confidence level (e.g., 0.95 for 95% CI).
        n_bootstrap: Number of bootstrap samples.
        random_seed: Seed for reproducibility.

    Returns:
        Dict with "ci_lower", "ci_upper", and "point_estimate".
    """
    import random

    if random_seed is not None:
        random.seed(random_seed)

    n = len(values)
    if n == 0:
        raise ValueError("Cannot bootstrap from empty values")

    def compute_stat(data: List[float]) -> float:
        if statistic == "mean":
            return sum(data) / len(data)
        elif statistic == "median":
            sorted_data = sorted(data)
            mid = len(data) // 2
            if len(data) % 2 == 0:
                return (sorted_data[mid - 1] + sorted_data[mid]) / 2
            return sorted_data[mid]
        elif statistic == "std":
            mean = sum(data) / len(data)
            variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
            return variance ** 0.5
        else:
            raise ValueError(f"Unknown statistic: {statistic}")

    original_stat = compute_stat(values)

    # Bootstrap sampling
    bootstrap_stats = []
    for _ in range(n_bootstrap):
        sample = [random.choice(values) for _ in range(n)]
        bootstrap_stats.append(compute_stat(sample))

    # Calculate confidence interval
    alpha = 1 - confidence
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100

    lower_ci = compute_stat(
        [v for v in bootstrap_stats if v <= sorted(bootstrap_stats)[int(len(bootstrap_stats) * lower_percentile / 100)]]
    )
    upper_ci = compute_stat(
        [v for v in bootstrap_stats if v >= sorted(bootstrap_stats)[int(len(bootstrap_stats) * upper_percentile / 100)]]
    )

    return {
        "ci_lower": round(lower_ci, 4),
        "ci_upper": round(upper_ci, 4),
        "point_estimate": round(original_stat, 4),
        "confidence": confidence,
    }
