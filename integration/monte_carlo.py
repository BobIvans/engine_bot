#!/usr/bin/env python3
# integration/monte_carlo.py
# Monte Carlo Harness for robustness verification.
# Executes strategy simulation multiple times with controlled randomization.

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.statistics import calculate_quantiles, calculate_win_probability, calculate_max_drawdown


def load_jsonl(file_path: str) -> List[Dict]:
    """Load JSONL file and return list of dicts."""
    trades = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return trades


def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    import yaml
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def apply_latency_jitter(latency_ms: float, sigma: float, rng: random.Random) -> float:
    """Apply jitter to latency value."""
    jitter = rng.gauss(0, sigma)
    return max(0, latency_ms + jitter)


def apply_slippage(price: float, slippage_pct: float, side: str, rng: random.Random) -> float:
    """Apply slippage to execution price."""
    slippage = price * slippage_pct * rng.uniform(-1, 1)
    if side == "buy":
        return price + slippage
    else:
        return price - slippage


def apply_price_noise(price: float, noise_pct: float, rng: random.Random) -> float:
    """Apply random noise to price."""
    return price * (1 + rng.uniform(-noise_pct, noise_pct))


def run_simulation(
    trades: List[Dict],
    config: Dict[str, Any],
    seed: int,
    shuffle: bool = True,
) -> Dict[str, float]:
    """
    Run a single simulation iteration.

    Args:
        trades: List of trade dicts.
        config: Configuration dict with randomization settings.
        seed: Random seed for this iteration.
        shuffle: Whether to shuffle trade order.

    Returns:
        Dict with total_pnl and max_drawdown_pct.
    """
    rng = random.Random(seed)

    # Make a copy of trades to avoid modifying original
    iteration_trades = [t.copy() for t in trades]

    # Optionally shuffle trade order
    if shuffle:
        rng.shuffle(iteration_trades)

    # Get configuration values
    sim_config = config.get("simulation", {})
    rand_config = config.get("pipeline", {}).get("randomization", {})

    initial_capital = sim_config.get("initial_capital", 10000.0)
    position_size_pct = sim_config.get("position_size_pct", 0.5)
    stop_loss_pct = sim_config.get("stop_loss_pct", 0.05)
    take_profit_pct = sim_config.get("take_profit_pct", 0.10)

    latency_sigma_range = rand_config.get("latency_sigma_range", [0.1, 0.5])
    slippage_range = rand_config.get("slippage_range", [0.001, 0.01])
    price_noise_range = rand_config.get("price_noise_range", [0.0, 0.02])

    # Randomize parameters for this iteration
    latency_sigma = rng.uniform(*latency_sigma_range)
    slippage_pct = rng.uniform(*slippage_range)
    price_noise_pct = rng.uniform(*price_noise_range)

    # Track portfolio state
    capital = initial_capital
    peak_capital = initial_capital
    max_drawdown = 0.0
    cumulative_pnl = 0.0
    trade_pnls = []

    # Simulate each trade
    for trade in iteration_trades:
        side = trade.get("side", "buy")
        amount = trade.get("amount", 0.0)
        base_price = trade.get("price", 100.0)

        # Apply randomization
        execution_price = apply_slippage(base_price, slippage_pct, side, rng)
        noisy_price = apply_price_noise(base_price, price_noise_pct, rng)
        simulated_latency = apply_latency_jitter(10.0, latency_sigma, rng)  # base 10ms

        # Calculate position size
        position_size = capital * position_size_pct
        if position_size > capital:
            position_size = capital

        # Calculate PnL for this trade
        if side == "buy":
            # Buy: price goes up = profit, down = loss
            price_change_pct = (noisy_price - base_price) / base_price
            trade_pnl = position_size * price_change_pct
        else:
            # Sell: price goes down = profit, up = loss
            price_change_pct = (base_price - noisy_price) / base_price
            trade_pnl = position_size * price_change_pct

        # Apply stop loss / take profit
        unrealized_pnl = trade_pnl
        if unrealized_pnl < -position_size * stop_loss_pct:
            unrealized_pnl = -position_size * stop_loss_pct
            trade_pnl = unrealized_pnl
        elif unrealized_pnl > position_size * take_profit_pct:
            unrealized_pnl = position_size * take_profit_pct
            trade_pnl = unrealized_pnl

        # Update capital
        capital += trade_pnl
        cumulative_pnl = capital - initial_capital

        # Track drawdown
        if capital > peak_capital:
            peak_capital = capital
        drawdown = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        trade_pnls.append(cumulative_pnl)

    # Calculate final metrics
    total_pnl = capital - initial_capital
    roi_pct = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0

    return {
        "total_pnl": total_pnl,
        "roi_pct": roi_pct,
        "max_drawdown_pct": max_drawdown * 100,
        "final_capital": capital,
    }


class MonteCarloRunner:
    """Monte Carlo simulation harness for strategy robustness verification."""

    def __init__(
        self,
        trades_path: str,
        config_path: str,
        runs: int = 1000,
        seed: int = 42,
        shuffle: bool = True,
    ):
        """
        Initialize the Monte Carlo runner.

        Args:
            trades_path: Path to JSONL file with trades.
            config_path: Path to YAML configuration file.
            runs: Number of simulation runs.
            seed: Master random seed.
            shuffle: Whether to shuffle trade order each iteration.
        """
        self.trades_path = trades_path
        self.config_path = config_path
        self.runs = runs
        self.seed = seed
        self.shuffle = shuffle

        # Load data once
        self.trades = load_jsonl(trades_path)
        self.config = load_yaml_config(config_path)

        # Results storage
        self.results: List[Dict[str, float]] = []
        self.roi_values: List[float] = []
        self.dd_values: List[float] = []

    def run_iteration(self, iteration: int) -> Dict[str, float]:
        """
        Run a single simulation iteration with controlled randomness.

        Args:
            iteration: Iteration number (used to derive seed).

        Returns:
            Dict with simulation results.
        """
        # Deterministic seed for this iteration
        iteration_seed = self.seed + iteration

        # Run simulation
        result = run_simulation(
            trades=self.trades,
            config=self.config,
            seed=iteration_seed,
            shuffle=self.shuffle,
        )

        return result

    def run_all(self, verbose: bool = True) -> Dict:
        """
        Run all simulation iterations.

        Args:
            verbose: Whether to print progress to stderr.

        Returns:
            Dict with aggregated statistics.
        """
        self.results = []
        self.roi_values = []
        self.dd_values = []

        # Run iterations
        for i in range(self.runs):
            result = self.run_iteration(i)
            self.results.append(result)
            self.roi_values.append(result["roi_pct"])
            self.dd_values.append(result["max_drawdown_pct"])

            # Progress output
            if verbose and self.runs > 10 and (i + 1) % (self.runs // 10) == 0:
                progress = ((i + 1) / self.runs) * 100
                print(f"[monte_carlo] Progress: {progress:.0f}%", file=sys.stderr)

        # Calculate statistics
        roi_quantiles = calculate_quantiles(self.roi_values, [5, 50, 95])
        dd_quantiles = calculate_quantiles(self.dd_values, [5, 50, 95])
        win_prob = calculate_win_probability(self.roi_values, threshold=0)

        return {
            "runs": self.runs,
            "roi_pct": {k: round(v, 4) for k, v in roi_quantiles.items()},
            "max_dd_pct": {k: round(v, 4) for k, v in dd_quantiles.items()},
            "win_prob": round(win_prob, 4),
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monte Carlo Harness for strategy robustness verification"
    )
    parser.add_argument(
        "--trades", required=True, help="Path to JSONL file with trades"
    )
    parser.add_argument(
        "--config", required=True, help="Path to YAML configuration file"
    )
    parser.add_argument(
        "--runs", type=int, default=1000, help="Number of simulation runs"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Master random seed"
    )
    parser.add_argument(
        "--shuffle", action="store_true", default=True,
        help="Shuffle trade order each iteration"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output"
    )

    args = parser.parse_args()

    # Load trades to show count
    trades = load_jsonl(args.trades)
    print(f"[monte_carlo] Loaded {len(trades)} trades. Running {args.runs} iterations...", file=sys.stderr)

    # Initialize runner
    runner = MonteCarloRunner(
        trades_path=args.trades,
        config_path=args.config,
        runs=args.runs,
        seed=args.seed,
        shuffle=args.shuffle,
    )

    # Run all iterations
    stats = runner.run_all(verbose=not args.quiet)

    # Output JSON result
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
