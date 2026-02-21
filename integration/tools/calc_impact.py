#!/usr/bin/env python3
"""
CLI utility for calculating AMM swap impact.

Usage:
    python3 -m integration.tools.calc_impact --amount 100 --res-in 1000 --res-out 2000
    python3 -m integration.tools.calc_impact --amount 100 --res-in 1000 --res-out 2000 --json
"""

import argparse
import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit('/integration/', 1)[0])

from strategy.amm_math import get_amount_out, get_price_impact_bps, get_execution_price


def main():
    parser = argparse.ArgumentParser(
        description="Calculate AMM swap amount and price impact"
    )
    parser.add_argument(
        "--amount",
        type=float,
        required=True,
        help="Amount of input token being sold"
    )
    parser.add_argument(
        "--res-in",
        type=float,
        required=True,
        help="Reserve of input token in the pool"
    )
    parser.add_argument(
        "--res-out",
        type=float,
        required=True,
        help="Reserve of output token in the pool"
    )
    parser.add_argument(
        "--fee",
        type=int,
        default=30,
        help="Swap fee in basis points (default: 30)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as single-line JSON"
    )
    
    args = parser.parse_args()
    
    try:
        # Calculate all metrics
        amount_out = get_amount_out(args.amount, args.res_in, args.res_out, args.fee)
        impact_bps = get_price_impact_bps(args.amount, args.res_in, args.res_out, args.fee)
        execution_price = get_execution_price(args.amount, args.res_in, args.res_out, args.fee)
        
        result = {
            "amount_out": amount_out,
            "impact_bps": impact_bps,
            "execution_price": execution_price
        }
        
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Amount Out: {amount_out}")
            print(f"Impact: {impact_bps} bps")
            print(f"Execution Price: {execution_price}")
            print(f"Mid Price: {args.res_out / args.res_in}")
        
    except ValueError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    except ZeroDivisionError:
        error_msg = "Zero reserves detected"
        if args.json:
            print(json.dumps({"error": error_msg}))
        print(error_msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
