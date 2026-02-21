#!/usr/bin/env python3
"""
Update Tier-1 wallet allowlist CLI tool.

Reads wallet addresses from CSV and updates the wallet allowlist YAML file.
"""

import argparse
import csv
import re
import sys
import yaml
from pathlib import Path


# Base58 regex pattern (matches Solana-style addresses)
BASE58_PATTERN = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


def validate_address(address: str) -> bool:
    """Validate a wallet address using base58 pattern."""
    return bool(BASE58_PATTERN.match(address.strip()))


def read_wallets_from_csv(csv_path: Path) -> list[str]:
    """Read wallet addresses from CSV file."""
    wallets = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        # Try 'wallet_address' column first, fallback to first column
        fieldnames = reader.fieldnames or []
        address_col = 'wallet_address' if 'wallet_address' in fieldnames else fieldnames[0] if fieldnames else None
        
        if not address_col:
            raise ValueError(f"CSV has no columns: {csv_path}")
        
        for row in reader:
            address = row.get(address_col, '').strip()
            if address:
                wallets.append(address)
    
    return wallets


def deduplicate_and_validate(wallets: list[str]) -> tuple[list[str], list[str]]:
    """Deduplicate and validate wallet addresses."""
    seen = set()
    valid_wallets = []
    invalid_wallets = []
    
    for address in wallets:
        if address in seen:
            continue
        
        seen.add(address)
        
        if validate_address(address):
            valid_wallets.append(address)
        else:
            invalid_wallets.append(address)
    
    return valid_wallets, invalid_wallets


def load_existing_yaml(yaml_path: Path) -> dict:
    """Load existing YAML file, preserving structure."""
    if yaml_path.exists():
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml(yaml_path: Path, data: dict) -> None:
    """Save data to YAML file."""
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def update_allowlist_yaml(yaml_path: Path, tier1_wallets: list[str]) -> None:
    """Update or create the wallet allowlist YAML."""
    existing = load_existing_yaml(yaml_path)
    
    # Preserve existing structure, update tier1 wallets
    existing['tier1_wallets'] = tier1_wallets
    
    save_yaml(yaml_path, existing)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Update Tier-1 wallet allowlist from CSV'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        type=Path,
        help='Input CSV file with wallet addresses'
    )
    parser.add_argument(
        '--out', '-o',
        required=True,
        type=Path,
        help='Output YAML file path (strategy/wallet_allowlist.yaml)'
    )
    
    args = parser.parse_args()
    
    # Read wallets from CSV
    try:
        wallets = read_wallets_from_csv(args.input)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not wallets:
        print("No wallet addresses found in CSV", file=sys.stderr)
        sys.exit(1)
    
    # Deduplicate and validate
    valid_wallets, invalid_wallets = deduplicate_and_validate(wallets)
    
    if invalid_wallets:
        print(f"Warning: {len(invalid_wallets)} invalid addresses ignored", file=sys.stderr)
        for addr in invalid_wallets[:5]:
            print(f"  - {addr}", file=sys.stderr)
        if len(invalid_wallets) > 5:
            print(f"  ... and {len(invalid_wallets) - 5} more", file=sys.stderr)
    
    if not valid_wallets:
        print("No valid wallet addresses found", file=sys.stderr)
        sys.exit(1)
    
    # Update YAML
    try:
        update_allowlist_yaml(args.out, valid_wallets)
    except Exception as e:
        print(f"Error writing YAML: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Silent on success - nothing printed to stdout/stderr
    sys.exit(0)


if __name__ == '__main__':
    main()
