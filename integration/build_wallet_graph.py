#!/usr/bin/env python3
"""
integration/build_wallet_graph.py

CLI wrapper for building wallet co-trade graphs.
Reads trades from JSONL/Parquet, invokes pure clustering logic, outputs graph JSON.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

# Import pure logic
from strategy.clustering import build_co_trade_graph, calculate_tier_scores, GraphStruct

# Import trade normalizer for reading trades
from integration.trade_normalizer import load_trades_jsonl, normalize_trade_record


def read_trades_jsonl(filepath: str) -> List[Dict[str, Any]]:
    """Read trades from JSONL file using trade_normalizer."""
    trades = []
    for item in load_trades_jsonl(filepath):
        # Skip rejects
        if isinstance(item, dict) and item.get("_reject"):
            continue
        # Convert Trade object to dict
        if hasattr(item, '__dataclass_fields__'):
            trade = {k: getattr(item, k) for k in item.__dataclass_fields__}
            trades.append(trade)
        else:
            trades.append(item)
    return trades


def read_trades_parquet(filepath: str) -> List[Dict[str, Any]]:
    """Read trades from Parquet file."""
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(filepath)
        records = table.to_pydict()
        n = len(records.get("ts", []))
        trades = []
        for i in range(n):
            trade = {}
            for key, vals in records.items():
                if i < len(vals):
                    trade[key] = vals[i]
            normalized = normalize_trade_record(trade)
            if not isinstance(normalized, dict) or not normalized.get("_reject"):
                trades.append(normalized)
        return trades
    except ImportError:
        raise RuntimeError("pyarrow not installed. Cannot read Parquet files.")


def build_graph_output(
    graph: GraphStruct,
    config: Dict[str, Any],
    include_tier_scores: bool = True
) -> Dict[str, Any]:
    """Build the complete output dictionary for the graph."""
    output = {
        "schema_version": "wallet_graph.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": {
            "window_sec": config.get("window_sec", 45.0),
            "min_co_trades": config.get("min_co_trades", 1)
        },
        "nodes": graph.to_dict()["nodes"],
        "edges": graph.to_dict()["edges"],
        "summary": graph.to_dict()["summary"]
    }

    if include_tier_scores:
        tier_scores = calculate_tier_scores(graph)
        output["tier_scores"] = tier_scores

    return output


def run_build_graph(
    trades_file: str,
    output_file: str,
    window_sec: float = 45.0,
    min_co_trades: int = 1,
    summary_json: bool = False
) -> Dict[str, Any]:
    """
    Main function to build wallet co-trade graph.

    Args:
        trades_file: Path to trades JSONL or Parquet file
        output_file: Path to output JSON file
        window_sec: Co-trade window in seconds
        min_co_trades: Minimum co-trades threshold
        summary_json: If True, output only summary to stdout

    Returns:
        Graph output dictionary
    """
    # Read trades
    if trades_file.endswith(".parquet"):
        trades = read_trades_parquet(trades_file)
    else:
        trades = read_trades_jsonl(trades_file)

    if not trades:
        raise ValueError(f"No trades found in {trades_file}")

    # Build graph using pure logic
    graph = build_co_trade_graph(
        trades=trades,
        window_sec=window_sec,
        min_co_trades=min_co_trades
    )

    # Build output
    config = {"window_sec": window_sec, "min_co_trades": min_co_trades}
    output = build_graph_output(graph, config)

    if summary_json:
        # Output only summary as single-line JSON to stdout
        summary = {
            "total_nodes": output["summary"]["total_nodes"],
            "total_edges": output["summary"]["total_edges"],
            "total_co_trades": output["summary"]["total_co_trades"]
        }
        print(json.dumps(summary))
    else:
        # Write full output to file
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Graph written to {output_file}", file=sys.stderr)

    return output


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build wallet co-trade graph from historical trades."
    )
    parser.add_argument(
        "--trades",
        required=True,
        help="Path to trades JSONL or Parquet file"
    )
    parser.add_argument(
        "--out",
        default="wallet_graph.json",
        help="Output JSON file path (default: wallet_graph.json)"
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=45.0,
        help="Co-trade window in seconds (default: 45)"
    )
    parser.add_argument(
        "--min-co-trades",
        type=int,
        default=1,
        help="Minimum co-trades threshold for edge inclusion (default: 1)"
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output only summary JSON to stdout (for scripting)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    try:
        output = run_build_graph(
            trades_file=args.trades,
            output_file=args.out,
            window_sec=args.window_sec,
            min_co_trades=args.min_co_trades,
            summary_json=args.summary_json
        )

        if args.verbose and not args.summary_json:
            print(f"Nodes: {output['summary']['total_nodes']}", file=sys.stderr)
            print(f"Edges: {output['summary']['total_edges']}", file=sys.stderr)
            print(f"Co-trades: {output['summary']['total_co_trades']}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
