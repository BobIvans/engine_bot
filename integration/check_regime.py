#!/usr/bin/env python3
"""integration/check_regime.py

CLI utility for checking the current Polymarket regime.

Usage:
    python -m integration.check_regime --market <id> [--mock-file <path>]
    python -m integration.check_regime --config <path> --market <id>

This script:
1. Loads configuration (or uses defaults)
2. Fetches market data from Polymarket (or mock file)
3. Calculates regime using strategy.regime module
4. Outputs JSON result to stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ingestion.sources.polymarket import PolymarketClient
from strategy.regime import RegimeResult, calculate_regime


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load regime configuration.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Configuration dictionary.
    """
    if config_path:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)

    # Default configuration
    return {
        "regime": {
            "bullish_threshold": 0.55,
            "crash_threshold": 0.3,
        }
    }


def main() -> int:
    """Main entrypoint."""
    parser = argparse.ArgumentParser(
        description="Check Polymarket regime and output JSON result."
    )
    parser.add_argument(
        "--market", "-m",
        required=True,
        help="Polymarket market ID or slug.",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--mock-file", "-M",
        help="Path to JSON file with mock market data.",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=2000,
        help="Request timeout in milliseconds (default: 2000).",
    )
    parser.add_argument(
        "--json", "-J",
        action="store_true",
        help="Output raw JSON to stdout (without status messages).",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    print(f"[check_regime] Market: {args.market}", file=sys.stderr)

    # Create client
    client = PolymarketClient(
        timeout_ms=args.timeout,
        mock_file=args.mock_file,
    )

    # Fetch market data
    market_data = client.fetch_market(args.market)

    if args.mock_file:
        print(f"[check_regime] Mode: MOCK", file=sys.stderr)
    else:
        print(f"[check_regime] Mode: LIVE", file=sys.stderr)

    # Extract probabilities
    probs = client.extract_probabilities(market_data)
    print(f"[check_regime] Data Quality: {probs['data_quality']}", file=sys.stderr)
    print(f"[check_regime] P_Yes: {probs['p_yes']}", file=sys.stderr)
    print(f"[check_regime] P_No: {probs['p_no']}", file=sys.stderr)

    # Calculate regime
    regime_config = config.get("regime", {})
    result = calculate_regime(probs, regime_config)

    # Output result
    output = {
        "market_id": args.market,
        "data_quality": probs["data_quality"],
        "p_yes": probs["p_yes"],
        "p_no": probs["p_no"],
        "p_crash": probs["p_crash"],
        "score": result.score,
        "risk_off": result.risk_off,
        "reason": result.reason,
    }

    print(f"[check_regime] Calculated Score: {result.score:.2f}", file=sys.stderr)
    print(f"[check_regime] Risk Off: {result.risk_off}", file=sys.stderr)
    print(f"[check_regime] Reason: {result.reason}", file=sys.stderr)

    if args.json:
        print(json.dumps(output))
    else:
        print(json.dumps(output, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
