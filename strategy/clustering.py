"""
strategy/clustering.py

Pure logic for building wallet co-trade graphs (Leader-Follower relationships).
No I/O - accepts trades, returns graph structure.
"""
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Union
from collections import defaultdict


@dataclass
class GraphNode:
    """Graph node with wallet metrics."""
    wallet: str
    out_degree: int = 0  # Times this wallet was a leader
    in_degree: int = 0   # Times this wallet followed someone


@dataclass
class GraphEdge:
    """Directed edge from leader to follower."""
    leader: str
    follower: str
    weight: int = 1  # Count of co-trades
    tokens: List[str] = None  # List of mints where this pattern occurred

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = []


class GraphStruct:
    """Container for the co-trade graph structure."""
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.edge_weights: Dict[Tuple[str, str], int] = defaultdict(int)
        self.edge_tokens: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "nodes": {
                wallet: {
                    "wallet": node.wallet,
                    "out_degree": node.out_degree,
                    "in_degree": node.in_degree
                }
                for wallet, node in self.nodes.items()
            },
            "edges": [
                {
                    "leader": edge.leader,
                    "follower": edge.follower,
                    "weight": edge.weight,
                    "tokens": edge.tokens
                }
                for edge in self.edges
            ],
            "summary": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_co_trades": sum(self.edge_weights.values())
            }
        }


def _parse_timestamp(ts_val: Union[str, int, float]) -> int:
    """Parse timestamp to unix seconds (int)."""
    if isinstance(ts_val, (int, float)):
        return int(ts_val)
    if isinstance(ts_val, str):
        ts_val = ts_val.strip()
        # Handle ISO-8601
        if "T" in ts_val or "-" in ts_val:
            from datetime import datetime
            if ts_val.endswith("Z"):
                ts_val = ts_val[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts_val)
            return int(dt.timestamp())
        # Handle unix timestamp string
        try:
            return int(float(ts_val))
        except ValueError:
            return 0
    return 0


def _normalize_trade(trade_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize trade dict to canonical format."""
    return {
        "ts": _parse_timestamp(trade_dict.get("ts", 0)),
        "wallet": str(trade_dict.get("wallet", "")),
        "mint": str(trade_dict.get("mint", "")),
        "side": str(trade_dict.get("side", "")).upper(),
        "tx_hash": str(trade_dict.get("tx_hash", "")),
        "price": float(trade_dict.get("price", 0)),
        "size_usd": float(trade_dict.get("size_usd", 0))
    }


def _get_sort_key(trade: Dict[str, Any]) -> Tuple[int, str]:
    """Get deterministic sort key for trades."""
    return (trade["ts"], trade["tx_hash"])


def build_co_trade_graph(
    trades: List[Any],
    window_sec: float = 45.0,
    min_co_trades: int = 1
) -> GraphStruct:
    """
    Build co-trade graph from list of trades.

    Args:
        trades: List of trade dicts or Trade objects
        window_sec: Time window in seconds for co-trading detection
        min_co_trades: Minimum co-trade count for an edge to be included

    Returns:
        GraphStruct containing nodes, edges, and metrics
    """
    # Parse trades if needed
    parsed_trades = []
    for t in trades:
        if isinstance(t, dict):
            # Already a dict, normalize it
            parsed_trades.append(_normalize_trade(t))
        else:
            # Assume Trade dataclass-like object
            trade_dict = {
                "ts": _parse_timestamp(getattr(t, "ts", 0)),
                "wallet": getattr(t, "wallet", ""),
                "mint": getattr(t, "mint", ""),
                "side": str(getattr(t, "side", "")).upper(),
                "tx_hash": getattr(t, "tx_hash", ""),
                "price": float(getattr(t, "price", 0)),
                "size_usd": float(getattr(t, "size_usd", 0))
            }
            parsed_trades.append(trade_dict)

    # Filter to only BUY trades and sort deterministically
    buy_trades = sorted(
        [t for t in parsed_trades if t["side"] == "BUY"],
        key=_get_sort_key
    )

    # Group by mint
    mint_to_trades: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for trade in buy_trades:
        mint_to_trades[trade["mint"]].append(trade)

    graph = GraphStruct()

    # Track all unique wallets
    all_wallets: set = set()

    # Find leader-follower pairs within window
    for mint, mint_trades in mint_to_trades.items():
        n = len(mint_trades)
        for i in range(n):
            leader = mint_trades[i]
            all_wallets.add(leader["wallet"])
            for j in range(i + 1, n):
                follower = mint_trades[j]
                all_wallets.add(follower["wallet"])
                delta = follower["ts"] - leader["ts"]

                if 0 < delta <= window_sec:
                    # Found a co-trade relationship
                    edge_key = (leader["wallet"], follower["wallet"])
                    graph.edge_weights[edge_key] += 1
                    graph.edge_tokens[edge_key].append(mint)

    # Add all wallets as nodes (even if they have no edges)
    for wallet in all_wallets:
        if wallet not in graph.nodes:
            graph.nodes[wallet] = GraphNode(wallet=wallet)

    # Build filtered edges and update degrees
    for (leader, follower), weight in graph.edge_weights.items():
        if weight >= min_co_trades:
            # Create edge
            edge = GraphEdge(
                leader=leader,
                follower=follower,
                weight=weight,
                tokens=list(set(graph.edge_tokens[(leader, follower)]))
            )
            graph.edges.append(edge)

            # Create/update nodes
            if leader not in graph.nodes:
                graph.nodes[leader] = GraphNode(wallet=leader)
            if follower not in graph.nodes:
                graph.nodes[follower] = GraphNode(wallet=follower)

            # Update degrees
            graph.nodes[leader].out_degree += weight
            graph.nodes[follower].in_degree += weight

    return graph


def calculate_tier_scores(graph: GraphStruct) -> Dict[str, Dict[str, float]]:
    """
    Calculate tier scores based on graph metrics.

    Returns:
        Dict mapping wallet -> score dict with 'leader_score', 'follower_score', 'total_score'
    """
    scores = {}
    max_out = max((n.out_degree for n in graph.nodes.values()), default=1)
    max_in = max((n.in_degree for n in graph.nodes.values()), default=1)

    for wallet, node in graph.nodes.items():
        leader_score = node.out_degree / max_out if max_out > 0 else 0
        follower_score = node.in_degree / max_in if max_in > 0 else 0

        # Leaders have high out_degree, followers have high in_degree
        # Total score weights being a leader more
        total_score = (0.6 * leader_score) + (0.4 * follower_score)

        scores[wallet] = {
            "leader_score": round(leader_score, 4),
            "follower_score": round(follower_score, 4),
            "total_score": round(total_score, 4),
            "out_degree": node.out_degree,
            "in_degree": node.in_degree
        }

    return scores
