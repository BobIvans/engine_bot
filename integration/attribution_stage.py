#!/usr/bin/env python3
"""
Performance Attribution CLI Stage.

Reads trades JSONL, decomposes PnL into components, outputs attribution report.

Usage:
    python -m integration.attribution_stage --trades <file> --out <file>

Output format: pnl_attribution.v1.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.analytics.attribution import (
    decompose_trade,
    aggregate_attribution,
    format_output,
    AttributionComponents,
)


def load_trades(file_handle: TextIO) -> List[Dict[str, Any]]:
    """Load trades from JSONL file."""
    trades = []
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        trades.append(json.loads(line))
    return trades


def validate_trade(trade: Dict[str, Any]) -> bool:
    """Validate trade has required fields."""
    required = ["price_signal", "price_entry", "price_exit", "qty"]
    return all(key in trade for key in required)


def main():
    parser = argparse.ArgumentParser(
        description="Performance Attribution: decompose PnL into components"
    )
    parser.add_argument(
        "--trades",
        type=str,
        required=True,
        help="Path to trades.jsonl"
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
        help="Enable verbose output to stderr"
    )
    
    args = parser.parse_args()
    
    # Load trades
    trades_path = Path(args.trades)
    if not trades_path.exists():
        print(f"Error: Trades file not found: {trades_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(trades_path, "r") as f:
        trades = load_trades(f)
    
    if not trades:
        print("Error: No trades found in input file", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Loaded {len(trades)} trades", file=sys.stderr)
    
    # Validate and decompose each trade
    components: List[AttributionComponents] = []
    invalid_count = 0
    
    for trade in trades:
        if not validate_trade(trade):
            invalid_count += 1
            continue
        
        component = decompose_trade(trade)
        components.append(component)
        
        if args.verbose:
            print(f"  {component.trade_id}: Theo={component.theoretical_pnl:.2f}, "
                  f"Drag={component.execution_drag:.2f}, Net={component.net_pnl:.2f}", 
                  file=sys.stderr)
    
    if invalid_count > 0:
        print(f"Warning: Skipped {invalid_count} trades with missing fields", file=sys.stderr)
    
    # Aggregate results
    report = aggregate_attribution(components)
    
    if args.verbose:
        print(f"Total Theoretical PnL: {report.total_theoretical_pnl:.2f}", file=sys.stderr)
        print(f"Total Execution Drag: {report.total_execution_drag:.2f} ({report.execution_drag_pct:.1f}%)", file=sys.stderr)
        print(f"Total Fee Drag: {report.total_fee_drag:.2f} ({report.fee_drag_pct:.1f}%)", file=sys.stderr)
        print(f"Total Net PnL: {report.total_net_pnl:.2f}", file=sys.stderr)
    
    # Write output
    output = format_output(report)
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    
    if args.verbose:
        print(f"Wrote attribution report to {out_path}", file=sys.stderr)
    
    # Print JSON summary to stdout (contract requirement)
    print(json.dumps(output))


if __name__ == "__main__":
    main()
