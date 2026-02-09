#!/usr/bin/env python3
"""
Co-Trade Timing Analysis CLI.

Reads trades.jsonl, computes wallet timing lags, outputs timing_distribution.v1.json.

Usage:
    python -m integration.timing_analysis --trades <file> --out <file>
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.analysis.timing import Trade, analyze_lags, format_output


def parse_trades(file_handle: TextIO) -> list[Trade]:
    """Parse trades from JSONL format."""
    trades = []
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        trades.append(Trade(
            wallet=data.get("wallet", data.get("wallet_address", "")),
            mint=data.get("mint", data.get("token_mint", "")),
            timestamp=data.get("timestamp", ""),
            side=data.get("side", "buy"),
            amount=float(data.get("amount", 0)),
            price=float(data.get("price", 0)),
        ))
    return trades


def main():
    parser = argparse.ArgumentParser(
        description="Co-Trade Timing Analysis: compute wallet entry lags"
    )
    parser.add_argument(
        "--trades",
        type=str,
        required=True,
        help="Input trades.jsonl file path"
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Read trades
    trades_path = Path(args.trades)
    if not trades_path.exists():
        print(f"Error: Trades file not found: {trades_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(trades_path, "r") as f:
        trades = parse_trades(f)
    
    if not trades:
        print("Error: No trades found in input file", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Loaded {len(trades)} trades from {trades_path}", file=sys.stderr)
    
    # Compute timing lags (pure logic)
    stats = analyze_lags(trades)
    
    # Format output
    output = format_output(stats)
    
    # Write result
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    
    if args.verbose:
        print(f"Wrote timing analysis to {out_path}", file=sys.stderr)
        print(f"Analyzed {len(stats)} wallets", file=sys.stderr)


if __name__ == "__main__":
    main()
