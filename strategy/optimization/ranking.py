"""
strategy/optimization/ranking.py

Performance metrics calculation and result ranking for strategy optimization.

Calculates Sharpe Ratio, Drawdown, ROI, and other metrics.

PR-V.2
"""
import sys
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class SweepResult:
    """Result of a single parameter configuration sweep."""
    params: Dict[str, Any]
    metrics: Dict[str, float]
    
    @property
    def sharpe(self) -> float:
        return self.metrics.get('sharpe_ratio', 0.0)
    
    @property
    def roi(self) -> float:
        return self.metrics.get('total_roi', 0.0)
    
    @property
    def max_drawdown(self) -> float:
        return self.metrics.get('max_drawdown', 0.0)


def calculate_metrics(trades: List[Dict]) -> Dict[str, float]:
    """
    Calculate performance metrics from a list of trades.
    
    Args:
        trades: List of trade dictionaries with 'pnl_pct' field
        
    Returns:
        Dictionary with performance metrics
    """
    if not trades:
        print("[ranking] WARNING: Empty trades list", file=sys.stderr)
        return {
            'total_roi': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
            'num_trades': 0,
        }
    
    # Extract PnL percentages
    pnls = np.array([t['pnl_pct'] for t in trades])
    num_trades = len(pnls)
    
    # Total ROI (sum of all PnLs, compounded)
    # Simple sum approximation for small percentages
    total_roi = float(np.sum(pnls))
    
    # Win rate
    wins = np.sum(pnls > 0)
    win_rate = float(wins) / num_trades if num_trades > 0 else 0.0
    
    # Build equity curve and calculate drawdown
    equity = np.cumsum(pnls)  # Simple equity curve from PnL sum
    running_max = np.maximum.accumulate(equity)
    drawdowns = running_max - equity
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
    
    # Sharpe Ratio: (mean_return / std_dev) * sqrt(num_trades)
    # Assuming annualization factor based on number of trades
    mean_return = np.mean(pnls)
    std_return = np.std(pnls, ddof=1) if num_trades > 1 else 1.0
    
    if std_return == 0:
        sharpe_ratio = 0.0
    else:
        # Annualize assuming each trade is one period
        sharpe_ratio = (mean_return / std_return) * np.sqrt(num_trades)
    
    return {
        'total_roi': total_roi,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'win_rate': win_rate,
        'num_trades': num_trades,
    }


def rank_configs(
    results: List[SweepResult],
    sort_by: str = 'sharpe_ratio',
    ascending: bool = False,
    top_n: Optional[int] = None,
) -> List[SweepResult]:
    """
    Rank sweep results by specified metric.
    
    Args:
        results: List of SweepResult objects
        sort_by: Metric name to sort by
        ascending: Sort ascending if True
        top_n: Return only top N results
        
    Returns:
        Sorted list of results
    """
    if not results:
        return []
    
    # Sort by specified metric
    sorted_results = sorted(
        results,
        key=lambda r: r.metrics.get(sort_by, 0.0),
        reverse=not ascending  # Descending for positive metrics
    )
    
    if top_n is not None:
        sorted_results = sorted_results[:top_n]
    
    return sorted_results


def calculate_combined_score(
    sharpe: float,
    roi: float,
    max_drawdown: float,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate combined score from multiple metrics.
    
    Args:
        sharpe: Sharpe ratio
        roi: Total ROI percentage
        max_drawdown: Maximum drawdown percentage
        weights: Optional weights for each metric
        
    Returns:
        Combined score
    """
    if weights is None:
        weights = {'sharpe': 0.5, 'roi': 0.3, 'drawdown': 0.2}
    
    # Normalize drawdown penalty (lower is better, so invert)
    drawdown_penalty = max(0, 1 - max_drawdown / 100)  # Assuming drawdown in %
    
    score = (
        weights['sharpe'] * sharpe +
        weights['roi'] * roi / 100 +  # Normalize ROI
        weights['drawdown'] * drawdown_penalty
    )
    
    return score


def get_best_config(results: List[SweepResult]) -> Optional[Dict]:
    """
    Get the best configuration from results.
    
    Args:
        results: List of SweepResult objects
        
    Returns:
        Dictionary with best config and metrics, or None if empty
    """
    ranked = rank_configs(results, sort_by='sharpe_ratio')
    
    if not ranked:
        return None
    
    best = ranked[0]
    
    return {
        'params': best.params,
        'metrics': best.metrics,
        'combined_score': calculate_combined_score(
            best.metrics.get('sharpe_ratio', 0),
            best.metrics.get('total_roi', 0),
            best.metrics.get('max_drawdown', 0),
        ),
    }
