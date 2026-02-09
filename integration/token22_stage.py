#!/usr/bin/env python3
"""
Token-2022 Extension Scanner CLI Stage.

Reads mint addresses, analyzes Token-2022 extensions, outputs risk flags.

Usage:
    python -m integration.token22_stage --mints <file> --account-data <file> --out <file>

Output format: token_extensions.v1.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.safety.token22 import (
    analyze_extensions_from_account_info,
    format_output,
    TokenSecurityProfile,
)


def load_mints(file_handle: TextIO) -> List[str]:
    """Load mint addresses from JSONL file."""
    mints = []
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        mint = data.get("mint", "")
        if mint:
            mints.append(mint)
    return mints


def load_account_data(file_path: Path) -> Dict[str, Any]:
    """Load mock account data from JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Token-2022 Extension Scanner: analyze extensions for security risks"
    )
    parser.add_argument(
        "--mints",
        type=str,
        required=True,
        help="Path to mints.jsonl"
    )
    parser.add_argument(
        "--account-data",
        type=str,
        required=True,
        help="Path to mock account data JSON"
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr"
    )
    
    args = parser.parse_args()
    
    # Load mints
    mints_path = Path(args.mints)
    if not mints_path.exists():
        print(f"Error: Mints file not found: {mints_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(mints_path, "r") as f:
        mints = load_mints(f)
    
    if not mints:
        print("Error: No mints found in input file", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Loaded {len(mints)} mints", file=sys.stderr)
    
    # Load account data (mock RPC response)
    account_data_path = Path(args.account_data)
    if not account_data_path.exists():
        print(f"Error: Account data file not found: {account_data_path}", file=sys.stderr)
        sys.exit(1)
    
    account_data = load_account_data(account_data_path)
    
    if args.verbose:
        print(f"Loaded account data for {len(account_data)} mints", file=sys.stderr)
    
    # Analyze each mint
    profiles: List[TokenSecurityProfile] = []
    
    for mint in mints:
        mint_data = account_data.get(mint)
        profile = analyze_extensions_from_account_info(mint, mint_data)
        profiles.append(profile)
        
        if args.verbose:
            flags = ", ".join(profile.risk_flags)
            status = "BLOCKED" if profile.is_blocked else "OK"
            print(f"  {mint}: {flags} [{status}]", file=sys.stderr)
    
    # Write JSONL output
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        for profile in profiles:
            f.write(json.dumps(profile.to_dict()) + "\n")
    
    if args.verbose:
        print(f"Wrote {len(profiles)} profiles to {out_path}", file=sys.stderr)
    
    # Print JSON summary to stdout (contract requirement)
    summary = format_output(profiles)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
