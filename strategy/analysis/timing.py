"""
Pure logic for Co-Trade Timing Analysis.

Computes execution lag between wallet entries for the same token mint.
Used to identify leaders (t=0 entries) vs followers (lagged entries).

Output format: timing_distribution.v1.json
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional
import json


@dataclass
class Trade:
    """Single trade event from trades.jsonl."""
    wallet: str
    mint: str
    timestamp: str  # ISO 8601 format
    side: str      # "buy" or "sell"
    amount: float
    price: float


@dataclass
class WalletTimingStats:
    """Timing statistics per wallet across all analyzed tokens."""
    avg_lag_sec: float           # Average lag in seconds
    median_lag_sec: float        # Median lag in seconds
    std_dev_lag_sec: float       # Standard deviation of lags
    zero_lag_entries: int        # Number of times wallet was first mover
    total_entries: int           # Total number of entries
    first_mover_ratio: float     # zero_lag_entries / total_entries
    
    def to_dict(self) -> dict:
        return {
            "avg_lag_sec": round(self.avg_lag_sec, 2),
            "median_lag_sec": round(self.median_lag_sec, 2),
            "std_dev_lag_sec": round(self.std_dev_lag_sec, 2) if self.std_dev_lag_sec else 0.0,
            "zero_lag_entries": self.zero_lag_entries,
            "total_entries": self.total_entries,
            "first_mover_ratio": round(self.first_mover_ratio, 2),
        }


def parse_timestamp(ts: str) -> float:
    """Parse ISO 8601 timestamp to seconds since epoch."""
    # Handle both formats: "2024-01-15T10:00:00Z" and "2024-01-15T10:00:00.123456Z"
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    from datetime import datetime
    dt = datetime.fromisoformat(ts)
    return dt.timestamp()


def analyze_lags(trades: Iterable[Trade]) -> Dict[str, WalletTimingStats]:
    """
    Analyze timing lags between wallet entries for the same token.
    
    Args:
        trades: Iterable of Trade objects, sorted by timestamp
        
    Returns:
        Dict mapping wallet address to WalletTimingStats
        
    Algorithm:
        1. Group trades by mint
        2. For each mint group, find t0 (first entry time)
        3. Calculate lag_i = t_i - t0 for each subsequent entry
        4. Aggregate stats per wallet across all mints
    """
    # Group trades by mint
    mint_groups: Dict[str, List[Trade]] = {}
    for trade in trades:
        if trade.mint not in mint_groups:
            mint_groups[trade.mint] = []
        mint_groups[trade.mint].append(trade)
    
    # Calculate lags per wallet
    wallet_lags: Dict[str, List[float]] = {}
    wallet_first_movers: Dict[str, int] = {}
    
    for mint, mint_trades in mint_groups.items():
        # Sort by timestamp within each mint
        sorted_trades = sorted(mint_trades, key=lambda t: parse_timestamp(t.timestamp))
        
        if not sorted_trades:
            continue
        
        # First trade defines t0 (reference time)
        t0 = parse_timestamp(sorted_trades[0].timestamp)
        first_wallet = sorted_trades[0].wallet
        
        # Track first movers
        if first_wallet not in wallet_first_movers:
            wallet_first_movers[first_wallet] = 0
        wallet_first_movers[first_wallet] += 1
        
        # Calculate lag for each trade
        for trade in sorted_trades:
            t_i = parse_timestamp(trade.timestamp)
            lag = t_i - t0  # lag in seconds
            
            if trade.wallet not in wallet_lags:
                wallet_lags[trade.wallet] = []
            wallet_lags[trade.wallet].append(lag)
    
    # Aggregate stats per wallet
    result: Dict[str, WalletTimingStats] = {}
    
    for wallet, lags in wallet_lags.items():
        if not lags:
            continue
            
        lags_sorted = sorted(lags)
        n = len(lags_sorted)
        
        avg_lag = sum(lags) / n
        median_lag = lags_sorted[n // 2] if n > 0 else 0.0
        
        # Calculate std dev
        if n > 1:
            variance = sum((lag - avg_lag) ** 2 for lag in lags) / (n - 1)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        
        zero_lag = sum(1 for lag in lags if lag == 0.0)
        first_movers = wallet_first_movers.get(wallet, 0)
        
        result[wallet] = WalletTimingStats(
            avg_lag_sec=avg_lag,
            median_lag_sec=median_lag,
            std_dev_lag_sec=std_dev,
            zero_lag_entries=zero_lag,
            total_entries=n,
            first_mover_ratio=first_movers / n if n > 0 else 0.0,
        )
    
    return result


def format_output(stats: Dict[str, WalletTimingStats]) -> dict:
    """Format timing stats for JSON output."""
    return {
        "version": "timing_distribution.v1",
        "wallets": {
            wallet: stats.to_dict() 
            for wallet, stats in stats.items()
        }
    }


if __name__ == "__main__":
    # Simple test
    test_trades = [
        Trade(wallet="W1", mint="A", timestamp="2024-01-15T10:00:00Z", side="buy", amount=100, price=1.0),
        Trade(wallet="W2", mint="A", timestamp="2024-01-15T10:00:05Z", side="buy", amount=50, price=1.0),
        Trade(wallet="W3", mint="A", timestamp="2024-01-15T10:00:10Z", side="buy", amount=75, price=1.0),
        Trade(wallet="W1", mint="B", timestamp="2024-01-15T11:00:00Z", side="buy", amount=200, price=2.0),
        Trade(wallet="W3", mint="B", timestamp="2024-01-15T11:00:02Z", side="buy", amount=30, price=2.0),
    ]
    
    result = analyze_lags(test_trades)
    output = format_output(result)
    print(json.dumps(output, indent=2))
