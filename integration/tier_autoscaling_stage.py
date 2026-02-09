#!/usr/bin/env python3
"""
Tier Auto-Scaling CLI Stage.

Reads current wallet tiers config and performance metrics,
calculates recommended tier changes (promote/demote),
outputs change log and new config suggestions.

Usage:
    python -m integration.tier_autoscaling_stage \
        --current <yaml> --metrics <jsonl> --out-changes <jsonl> --out-config <yaml>

Output:
    tier_changes.v1.jsonl
    wallet_tiers.next.yaml
"""

import argparse
import json
import yaml
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.tiers.autoscaler import calculate_tier_changes, AutoscalingResult


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    data = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def save_yaml(data: Dict[str, Any], file_path: Path):
    """Save dictionary to YAML file."""
    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(
        description="Tier Auto-Scaling: manage wallet tiers based on performance"
    )
    parser.add_argument(
        "--current",
        type=str,
        required=True,
        help="Path to current tiers YAML"
    )
    parser.add_argument(
        "--metrics",
        type=str,
        required=True,
        help="Path to performance metrics JSONL"
    )
    parser.add_argument(
        "--out-changes",
        type=str,
        required=True,
        help="Output path for change log JSONL"
    )
    parser.add_argument(
        "--out-config",
        type=str,
        required=True,
        help="Output path for new tiers YAML"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr"
    )
    
    args = parser.parse_args()
    
    # Load inputs
    current_path = Path(args.current)
    if not current_path.exists():
        print(f"Error: Current tiers file not found: {current_path}", file=sys.stderr)
        sys.exit(1)
        
    metrics_path = Path(args.metrics)
    if not metrics_path.exists():
        print(f"Error: Metrics file not found: {metrics_path}", file=sys.stderr)
        sys.exit(1)
    
    current_tiers = load_yaml(current_path)
    metrics = load_jsonl(metrics_path)
    
    if args.verbose:
        print(f"Loaded config with {len(current_tiers)} tiers", file=sys.stderr)
        print(f"Loaded {len(metrics)} wallet metrics", file=sys.stderr)
    
    # Run autoscaling logic
    # TODO: Load params from config if available, using defaults for now
    result = calculate_tier_changes(current_tiers, metrics)
    
    # Output change log
    changes_path = Path(args.out_changes)
    change_log = result.get_change_log()
    with open(changes_path, "w") as f:
        for change in change_log:
            f.write(json.dumps(change) + "\n")
            
    if args.verbose:
        print(f"Generated {len(change_log)} tier changes", file=sys.stderr)
        for change in change_log:
            print(f"  {change['action']} {change['wallet']}: {change['reason']}", file=sys.stderr)
            
    # Output new config
    config_path = Path(args.out_config)
    save_yaml(result.new_config, config_path)
    
    if args.verbose:
        print(f"Wrote new config to {config_path}", file=sys.stderr)
    
    # Print JSON summary to stdout (contract requirement)
    summary = {
        "total_changes": len(change_log),
        "promotions": sum(1 for c in change_log if c["action"] == "PROMOTE"),
        "demotions": sum(1 for c in change_log if c["action"] == "DEMOTE"),
        "config_path": str(config_path)
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
