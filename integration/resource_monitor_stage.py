#!/usr/bin/env python3
"""
Resource Monitor CLI Stage.

Reads usage stats and limits config, checks quotas, outputs status report.

Usage:
    python -m integration.resource_monitor_stage --usage <file> --limits <file> --out <file>

Output format: resource_status.v1.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.ops.resource_monitor import check_quotas, format_output


def load_json(file_path: Path) -> Dict[str, Any]:
    """Load JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    import yaml
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def load_config(file_path: Path) -> Dict[str, Any]:
    """Load config file (JSON or YAML)."""
    suffix = file_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_yaml(file_path)
    else:
        return load_json(file_path)


def main():
    parser = argparse.ArgumentParser(
        description="Resource Monitor: check quota usage against limits"
    )
    parser.add_argument(
        "--usage",
        type=str,
        required=True,
        help="Path to usage stats JSON"
    )
    parser.add_argument(
        "--limits",
        type=str,
        required=True,
        help="Path to limits config (YAML or JSON)"
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
    
    # Load usage stats
    usage_path = Path(args.usage)
    if not usage_path.exists():
        print(f"Error: Usage file not found: {usage_path}", file=sys.stderr)
        sys.exit(1)
    
    usage = load_json(usage_path)
    
    if args.verbose:
        print(f"Loaded {len(usage)} usage metrics", file=sys.stderr)
    
    # Load limits config
    limits_path = Path(args.limits)
    if not limits_path.exists():
        print(f"Error: Limits file not found: {limits_path}", file=sys.stderr)
        sys.exit(1)
    
    limits = load_config(limits_path)
    
    if args.verbose:
        print(f"Loaded limits config with {len(limits)} entries", file=sys.stderr)
    
    # Check quotas (pure logic)
    report = check_quotas(usage, limits)
    
    # Output alerts to stderr
    for alert in report.alerts:
        print(f"[resource_monitor] {alert}", file=sys.stderr)
    
    if args.verbose:
        print(f"Global status: {report.global_status}", file=sys.stderr)
        for name, detail in report.details.items():
            print(f"  {name}: {detail.utilization_pct*100:.1f}% [{detail.status}]", file=sys.stderr)
    
    # Write output
    output = format_output(report)
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    
    if args.verbose:
        print(f"Wrote status report to {out_path}", file=sys.stderr)
    
    # Print JSON summary to stdout (contract requirement)
    print(json.dumps(output))


if __name__ == "__main__":
    main()
