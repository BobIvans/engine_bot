"""analysis/wallet_graph.py

Pure functions for building co-trade graph and clustering wallets.

This module provides pure functions without side effects for:
- Building co-trade adjacency matrix from normalized trades
- Detecting clusters based on co-trade frequency
- Computing leader/follower metrics within clusters
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


# Constants
CO_TRADE_WINDOW_MS = 60_000  # 60 seconds in milliseconds
MIN_CO_TRADES_DEFAULT = 3  # Minimum co-trades to establish cluster connection


@dataclass(frozen=True)
class TradeNorm:
    """Normalized trade for clustering."""
    wallet_addr: str
    mint: str
    ts_ms: int  # Timestamp in milliseconds
    side: str  # 'buy' or 'sell'
    size_usd: float


@dataclass(frozen=True)
class WalletClusterMetrics:
    """Per-wallet clustering metrics."""
    wallet_addr: str
    cluster_label: Optional[int] = None
    leader_score: Optional[float] = None  # 0.0 to 1.0
    follower_lag_ms: Optional[int] = None  # Median lag from leader
    co_trade_count: Optional[int] = None  # Total co-trades in cluster


def build_co_trade_matrix(
    trades: List[TradeNorm],
    window_ms: int = CO_TRADE_WINDOW_MS
) -> Dict[Tuple[str, str], int]:
    """Build co-trade adjacency matrix from normalized trades.
    
    Args:
        trades: List of normalized trades.
        window_ms: Time window in milliseconds for co-trade detection.
    
    Returns:
        Sparse adjacency matrix as dict: {(wallet_a, wallet_b): count}
        Keys are sorted (min, max) to ensure consistency.
    """
    # Group trades by mint
    trades_by_mint: Dict[str, List[TradeNorm]] = {}
    for trade in trades:
        if trade.side != 'buy' or trade.size_usd < 2000:
            continue  # Filter: only large buys
        if trade.mint not in trades_by_mint:
            trades_by_mint[trade.mint] = []
        trades_by_mint[trade.mint].append(trade)
    
    # Build co-trade matrix
    co_trade_matrix: Dict[Tuple[str, str], int] = {}
    
    for mint, mint_trades in trades_by_mint.items():
        # Sort by timestamp
        sorted_trades = sorted(mint_trades, key=lambda t: t.ts_ms)
        n = len(sorted_trades)
        
        # Compare all pairs within window
        for i in range(n):
            for j in range(i + 1, n):
                trade_i = sorted_trades[i]
                trade_j = sorted_trades[j]
                
                # Check if within time window
                if trade_j.ts_ms - trade_i.ts_ms > window_ms:
                    break  # Too far, no more pairs for this i
                
                # Record co-trade (sorted key for consistency)
                wallet_a = trade_i.wallet_addr
                wallet_b = trade_j.wallet_addr
                if wallet_a == wallet_b:
                    continue  # Same wallet, skip
                
                key = (min(wallet_a, wallet_b), max(wallet_a, wallet_b))
                co_trade_matrix[key] = co_trade_matrix.get(key, 0) + 1
    
    return co_trade_matrix


def detect_clusters(
    co_trade_matrix: Dict[Tuple[str, str], int],
    min_co_trades: int = MIN_CO_TRADES_DEFAULT
) -> Dict[str, int]:
    """Detect clusters based on co-trade threshold.
    
    Args:
        co_trade_matrix: Sparse adjacency matrix from build_co_trade_matrix.
        min_co_trades: Minimum co-trades to establish cluster connection.
    
    Returns:
        Mapping of wallet_addr -> cluster_id.
    """
    # Build graph from matrix (edges where co_trade_count >= min_co_trades)
    graph: Dict[str, Set[str]] = {}
    
    for (wallet_a, wallet_b), count in co_trade_matrix.items():
        if count >= min_co_trades:
            if wallet_a not in graph:
                graph[wallet_a] = set()
            if wallet_b not in graph:
                graph[wallet_b] = set()
            graph[wallet_a].add(wallet_b)
            graph[wallet_b].add(wallet_a)
    
    # Find connected components via BFS
    clusters: Dict[str, int] = {}
    cluster_id = 0
    
    visited: Set[str] = set()
    
    for wallet in graph:
        if wallet in visited:
            continue
        
        # Start new cluster
        queue = [wallet]
        visited.add(wallet)
        clusters[wallet] = cluster_id
        
        while queue:
            current = queue.pop(0)
            for neighbor in graph.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    clusters[neighbor] = cluster_id
                    queue.append(neighbor)
        
        cluster_id += 1
    
    return clusters


def compute_leader_metrics(
    trades: List[TradeNorm],
    clusters: Dict[str, int]
) -> Dict[str, WalletClusterMetrics]:
    """Compute leader/follower metrics within clusters.
    
    Args:
        trades: List of normalized trades.
        clusters: Mapping of wallet_addr -> cluster_id.
    
    Returns:
        Mapping of wallet_addr -> WalletClusterMetrics.
    """
    # Group trades by mint
    trades_by_mint: Dict[str, List[TradeNorm]] = {}
    for trade in trades:
        if trade.side != 'buy':
            continue
        if trade.mint not in trades_by_mint:
            trades_by_mint[trade.mint] = []
        trades_by_mint[trade.mint].append(trade)
    
    # Initialize metrics
    metrics: Dict[str, WalletClusterMetrics] = {}
    leader_stats: Dict[str, Dict[str, Any]] = {}  # wallet -> {lead_count, lags}
    cluster_wallets: Dict[int, Set[str]] = {}
    
    for wallet in clusters:
        metrics[wallet] = WalletClusterMetrics(wallet_addr=wallet)
        leader_stats[wallet] = {"lead_count": 0, "lags": []}
        cid = clusters[wallet]
        if cid not in cluster_wallets:
            cluster_wallets[cid] = set()
        cluster_wallets[cid].add(wallet)
    
    # For each token, find leader and compute lags
    for mint, mint_trades in trades_by_mint.items():
        # Filter to only clustered wallets
        clustered_trades = [t for t in mint_trades if t.wallet_addr in clusters]
        if len(clustered_trades) < 2:
            continue
        
        # Sort by timestamp to find leader
        sorted_trades = sorted(clustered_trades, key=lambda t: t.ts_ms)
        leader = sorted_trades[0].wallet_addr
        
        # Update leader stats
        if leader in leader_stats:
            leader_stats[leader]["lead_count"] += 1
        
        # Compute lags for followers
        leader_ts = sorted_trades[0].ts_ms
        for trade in sorted_trades[1:]:
            if trade.wallet_addr in leader_stats:
                lag = trade.ts_ms - leader_ts
                leader_stats[trade.wallet_addr]["lags"].append(lag)
    
    # Compute final metrics
    for wallet, stats in leader_stats.items():
        cluster_id = clusters.get(wallet)
        co_trades = sum(1 for _, c in clusters.items() if c == cluster_id) - 1
        
        # Leader score: lead_count / total_opportunities
        # Estimate opportunities as number of cluster members
        cluster_size = len(cluster_wallets.get(cluster_id, {wallet}))
        lead_count = stats["lead_count"]
        leader_score = 0.0
        if cluster_size > 1 and lead_count > 0:
            # Normalize: higher lead count = higher score
            leader_score = min(1.0, lead_count / (cluster_size * 0.5))
        
        # Follower lag: median of all lags
        lags = stats["lags"]
        follower_lag_ms = None
        if lags:
            sorted_lags = sorted(lags)
            n = len(sorted_lags)
            follower_lag_ms = sorted_lags[n // 2] if n % 2 == 1 else (sorted_lags[n//2 - 1] + sorted_lags[n//2]) // 2
        
        metrics[wallet] = WalletClusterMetrics(
            wallet_addr=wallet,
            cluster_label=cluster_id,
            leader_score=leader_score if leader_stats[wallet]["lead_count"] > 0 else 0.0,
            follower_lag_ms=follower_lag_ms,
            co_trade_count=co_trades if cluster_id is not None else 0,
        )
    
    return metrics


def build_clusters(
    trades: List[TradeNorm],
    min_co_trades: int = MIN_CO_TRADES_DEFAULT,
    window_ms: int = CO_TRADE_WINDOW_MS
) -> Dict[str, WalletClusterMetrics]:
    """Build wallet clusters and compute metrics in one pass.
    
    This is the main entry point for clustering.
    
    Args:
        trades: List of normalized trades.
        min_co_trades: Minimum co-trades to establish cluster connection.
        window_ms: Time window in milliseconds for co-trade detection.
    
    Returns:
        Mapping of wallet_addr -> WalletClusterMetrics.
    """
    # Step 1: Build co-trade matrix
    co_trade_matrix = build_co_trade_matrix(trades, window_ms)
    
    # Step 2: Detect clusters
    clusters = detect_clusters(co_trade_matrix, min_co_trades)
    
    # Step 3: Compute leader/follower metrics
    metrics = compute_leader_metrics(trades, clusters)
    
    return metrics
