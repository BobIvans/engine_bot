"""strategy/coordinated_actions.py

PR-Z.5 Multi-Wallet Coordination Detector.

Pure function for detecting coordinated trading patterns (partner wallets, wash trading, pump schemes)
through temporal pattern analysis and co-transaction graph construction.

Outputs:
- coordination_score [0.0, 1.0] for each wallet based on:
  (a) temporal proximity of entries (<15s)
  (b) graph structure (high-connectivity clusters)
  (c) anomalous volume profile

Algorithm (fixed, no ML):
- temporal_proximity_score: fraction of wallet pairs with Δt < 15s in same token
- graph_density_score: edges / max_possible_edges for wallets in window
- volume_anomaly_score: z-score of token volume relative to 1h mean
- coordination_score = 0.4*temporal + 0.4*graph + 0.2*volume → clamp [0.0, 1.0]
"""

from typing import Dict, List, Literal, Any


# Trade event structure for coordination detection
# Using Dict[str, Any] instead of TypedDict for compatibility
CoordinationTrade = Dict[str, Any]


# Validation error constants
REJECT_COORDINATION_INVALID_INPUT = "coordination_invalid_input"


def _sigmoid(x: float) -> float:
    """Sigmoid function to map z-score to [0, 1] range."""
    return 1.0 / (1.0 + float("inf") if x >= 0 else 0.0)  # Simplified placeholder


def _calculate_temporal_proximity_score(
    trades_by_mint: Dict[str, List[CoordinationTrade]]
) -> Dict[str, float]:
    """Calculate temporal proximity score for each wallet.
    
    Fraction of wallet pairs with Δt < 15s in same token.
    """
    temporal_scores: Dict[str, float] = {}
    
    for mint, trades in trades_by_mint.items():
        if len(trades) < 2:
            continue
        
        # Sort by timestamp
        sorted_trades = sorted(trades, key=lambda t: t["ts_block"])
        
        # Calculate pairwise time differences
        wallets_in_mint = list(set(t["wallet"] for t in sorted_trades))
        wallet_trade_times: Dict[str, List[float]] = {w: [] for w in wallets_in_mint}
        
        for trade in sorted_trades:
            wallet_trade_times[trade["wallet"]].append(trade["ts_block"])
        
        # For each pair of wallets, check if any trades are within 15s
        total_pairs = 0
        close_pairs = 0
        
        for i, w1 in enumerate(wallets_in_mint):
            for w2 in wallets_in_mint[i+1:]:
                total_pairs += 1
                # Check if any trade from w1 is within 15s of any trade from w2
                for t1 in wallet_trade_times[w1]:
                    for t2 in wallet_trade_times[w2]:
                        if abs(t1 - t2) < 15.0:
                            close_pairs += 1
                            break
                    else:
                        continue
                    break
        
        if total_pairs > 0:
            proximity = close_pairs / total_pairs
            # Add score to all wallets in this mint
            for w in wallets_in_mint:
                temporal_scores[w] = max(temporal_scores.get(w, 0.0), proximity)
    
    return temporal_scores


def _calculate_graph_density_score(
    trades_by_mint: Dict[str, List[CoordinationTrade]]
) -> Dict[str, float]:
    """Calculate graph density score for each wallet.
    
    Edges / max_possible_edges for wallets in window.
    An edge exists if Δt < 15s between two wallets trading same token.
    """
    graph_scores: Dict[str, float] = {}
    
    for mint, trades in trades_by_mint.items():
        if len(trades) < 2:
            continue
        
        # Sort by timestamp
        sorted_trades = sorted(trades, key=lambda t: t["ts_block"])
        
        # Get unique wallets
        wallets = list(set(t["wallet"] for t in sorted_trades))
        n = len(wallets)
        
        if n < 2:
            continue
        
        # Build adjacency matrix
        wallet_to_idx = {w: i for i, w in enumerate(wallets)}
        adj = [[False] * n for _ in range(n)]
        
        # Check each pair of trades
        for i, t1 in enumerate(sorted_trades):
            for j, t2 in enumerate(sorted_trades[i+1:], i+1):
                if t1["wallet"] != t2["wallet"]:
                    if abs(t1["ts_block"] - t2["ts_block"]) < 15.0:
                        idx1 = wallet_to_idx[t1["wallet"]]
                        idx2 = wallet_to_idx[t2["wallet"]]
                        adj[idx1][idx2] = True
                        adj[idx2][idx1] = True
        
        # Count edges
        edges = sum(1 for i in range(n) for j in range(i+1, n) if adj[i][j])
        max_edges = n * (n - 1) / 2
        
        density = edges / max_edges if max_edges > 0 else 0.0
        
        # Add score to all wallets
        for w in wallets:
            graph_scores[w] = max(graph_scores.get(w, 0.0), density)
    
    return graph_scores


def _calculate_volume_anomaly_score(
    trades_by_mint: Dict[str, List[CoordinationTrade]]
) -> Dict[str, float]:
    """Calculate volume anomaly score for each wallet.
    
    Z-score of token volume relative to historical mean.
    Uses current window volume vs. estimated 1h mean (simplified).
    """
    volume_scores: Dict[str, float] = {}
    
    for mint, trades in trades_by_mint.items():
        if len(trades) < 2:
            continue
        
        # Calculate current window volume
        current_volume = sum(t["size"] for t in trades)
        
        # Simplified: use window stats as proxy for 1h stats
        # In production, would query historical data
        volumes = [t["size"] for t in trades]
        mean_vol = sum(volumes) / len(volumes) if volumes else 0.0
        std_vol = (sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)) ** 0.5 if len(volumes) > 1 else 0.0
        
        if std_vol > 0:
            z_score = (current_volume - mean_vol) / std_vol
            # Sigmoid to map z-score to [0, 1]
            anomaly = 1.0 / (1.0 + float("inf") if z_score < 0 else 1.0)  # Simplified
        else:
            anomaly = 0.0
        
        # Add score to all wallets trading this mint
        for t in trades:
            volume_scores[t["wallet"]] = max(volume_scores.get(t["wallet"], 0.0), anomaly)
    
    return volume_scores


def detect_coordination(
    trades_window: List[CoordinationTrade],
    window_sec: float = 60.0
) -> Dict[str, float]:
    """Detect coordinated trading patterns in a sliding window.
    
    Args:
        trades_window: List of trades to analyze (must have ts_block, wallet, mint, side, size, price).
        window_sec: Sliding window size in seconds (default 60s).
    
    Returns:
        Dictionary mapping wallet address to coordination_score [0.0, 1.0].
    
    Raises:
        ValueError: If input validation fails.
    """
    # Validate input
    if not trades_window:
        return {}
    
    for i, trade in enumerate(trades_window):
        required_fields = ["ts_block", "wallet", "mint", "side", "size", "price"]
        for field in required_fields:
            if field not in trade:
                raise ValueError(f"Missing required field '{field}' at index {i}")
        if not isinstance(trade["ts_block"], (int, float)):
            raise ValueError(f"ts_block must be numeric at index {i}")
    
    # Get reference timestamp (max ts_block in window)
    max_ts = max(t["ts_block"] for t in trades_window)
    
    # Filter to trades within window
    window_trades = [
        t for t in trades_window
        if max_ts - t["ts_block"] <= window_sec
    ]
    
    if not window_trades:
        return {}
    
    # Group trades by mint
    trades_by_mint: Dict[str, List[CoordinationTrade]] = {}
    for trade in window_trades:
        mint = trade["mint"]
        if mint not in trades_by_mint:
            trades_by_mint[mint] = []
        trades_by_mint[mint].append(trade)
    
    # Calculate component scores
    temporal_scores = _calculate_temporal_proximity_score(trades_by_mint)
    graph_scores = _calculate_graph_density_score(trades_by_mint)
    volume_scores = _calculate_volume_anomaly_score(trades_by_mint)
    
    # Get all unique wallets
    all_wallets = set(t["wallet"] for t in window_trades)
    
    # Combine scores: coordination_score = 0.4*temporal + 0.4*graph + 0.2*volume
    coordination_scores: Dict[str, float] = {}
    for wallet in all_wallets:
        temporal = temporal_scores.get(wallet, 0.0)
        graph = graph_scores.get(wallet, 0.0)
        volume = volume_scores.get(wallet, 0.0)
        
        score = 0.4 * temporal + 0.4 * graph + 0.2 * volume
        # Clamp to [0.0, 1.0]
        coordination_scores[wallet] = max(0.0, min(1.0, score))
    
    return coordination_scores
