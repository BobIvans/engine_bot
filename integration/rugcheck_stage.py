#!/usr/bin/env python3
"""
RugCheck Pipeline Stage.

Enriches token snapshots with external risk evaluation from RugCheck API.
Uses fail-open architecture: if API is unavailable, returns neutral score.

Usage:
    python -m integration.rugcheck_stage --mints <file> --out <file>
    python -m integration.rugcheck_stage --dump-risk
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, TextIO

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from integration.adapters.rugcheck import RugCheckClient
from strategy.safety.external_risk import normalize_rugcheck_report, format_output


def parse_mints(file_handle: TextIO) -> List[str]:
    """Parse list of mints from input file (one per line or JSON array)."""
    content = file_handle.read().strip()
    
    if not content:
        return []
    
    # Try JSON array first
    try:
        mints = json.loads(content)
        if isinstance(mints, list):
            return [str(m) for m in mints]
    except json.JSONDecodeError:
        pass
    
    # Fall back to one-per-line
    return [line.strip() for line in content.split("\n") if line.strip()]


def enrich_mints(
    mints: List[str],
    client: RugCheckClient,
    verbose: bool = False
) -> Dict[str, dict]:
    """
    Enrich list of mints with risk profiles.
    
    Args:
        mints: List of token mint addresses
        client: RugCheckClient instance
        verbose: Enable verbose logging
        
    Returns:
        Dict mapping mint to risk evaluation profile
    """
    results = {}
    
    for i, mint in enumerate(mints):
        if verbose:
            print(f"[rugcheck_stage] Processing {i+1}/{len(mints)}: {mint[:8]}...", file=sys.stderr)
        
        # Get raw result from API
        raw_result = client.get_risk_profile(mint)
        
        # Normalize to RiskProfile
        # Check if this is already a normalized result (fail-open case)
        if "flags" in raw_result and "api_unavailable" in raw_result.get("flags", []):
            # Already normalized fail-open result
            results[mint] = raw_result
        else:
            # Need to normalize
            profile = normalize_rugcheck_report(raw_result)
            results[mint] = format_output(profile)
    
    return results


def dump_risk_eval(results: Dict[str, dict], out_path: Path) -> None:
    """
    Write risk evaluations to output file (risk_eval.v1 format).
    
    Args:
        results: Dict of mint -> risk profile
        out_path: Output file path
    """
    with open(out_path, "w") as f:
        for mint, profile in results.items():
            f.write(json.dumps(profile) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="RugCheck Pipeline Stage: Enrich tokens with external risk evaluation"
    )
    parser.add_argument(
        "--mints",
        type=str,
        help="Input file with list of mints (one per line or JSON array)"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output file for risk evaluations (JSONL format)"
    )
    parser.add_argument(
        "--dump-risk",
        action="store_true",
        help="Dump risk evaluation to stdout (for testing)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--mock",
        type=str,
        help="Path to mock JSON file (for testing without API)"
    )
    
    args = parser.parse_args()
    
    # Handle mock mode for testing
    if args.mock:
        with open(args.mock, "r") as f:
            mock_data = json.load(f)
        
        # Normalize mock data
        profile = normalize_rugcheck_report(mock_data)
        output = format_output(profile)
        
        if args.dump_risk:
            print(json.dumps(output, indent=2))
        else:
            print(f"Mint: {output['mint']}", file=sys.stderr)
            print(f"Score: {output['score']}", file=sys.stderr)
            print(f"Flags: {output['flags']}", file=sys.stderr)
        
        return 0
    
    # Validate arguments
    if not args.mints:
        parser.error("--mints or --mock required")
    
    # Read mints
    mints_path = Path(args.mints)
    if not mints_path.exists():
        print(f"Error: Mints file not found: {mints_path}", file=sys.stderr)
        return 1
    
    with open(mints_path, "r") as f:
        mints = parse_mints(f)
    
    if not mints:
        print("Error: No mints found in input file", file=sys.stderr)
        return 1
    
    if args.verbose:
        print(f"[rugcheck_stage] Loaded {len(mints)} mints", file=sys.stderr)
    
    # Initialize client
    client = RugCheckClient()
    
    # Enrich mints with risk profiles
    start_time = time.time()
    results = enrich_mints(mints, client, args.verbose)
    elapsed = time.time() - start_time
    
    if args.verbose:
        print(f"[rugcheck_stage] Processed {len(results)} mints in {elapsed:.2f}s", file=sys.stderr)
        print(f"[rugcheck_stage] Cache stats: {client.get_cache_stats()}", file=sys.stderr)
    
    # Output results
    if args.dump_risk:
        # Write to stdout in JSONL format
        for mint, profile in results.items():
            print(json.dumps(profile))
    elif args.out:
        # Write to file
        dump_risk_eval(results, Path(args.out))
        if args.verbose:
            print(f"[rugcheck_stage] Wrote {len(results)} profiles to {args.out}", file=sys.stderr)
    else:
        # Default: write to risk_eval.v1.json in current directory
        default_out = Path("risk_eval.v1.jsonl")
        dump_risk_eval(results, default_out)
        if args.verbose:
            print(f"[rugcheck_stage] Wrote {len(results)} profiles to {default_out}", file=sys.stderr)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
