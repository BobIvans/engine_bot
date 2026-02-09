#!/usr/bin/env python3
"""
Feature Drift Detection CLI Stage.

Reads current feature batch and baseline stats, computes PSI per feature,
outputs drift_report.v1.json.

Usage:
    python -m integration.feature_drift_stage --baseline <file> --current <file> --out <file>
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO, List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.monitoring.drift import analyze_drift, format_output


def load_baseline(file_path: Path) -> Dict:
    """Load baseline statistics from JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def stream_features(file_handle: TextIO) -> List[Dict[str, float]]:
    """Stream read features from JSONL file."""
    features = []
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        features.append(data)
    return features


def main():
    parser = argparse.ArgumentParser(
        description="Feature Drift Detection: compute PSI for monitored features"
    )
    parser.add_argument(
        "--baseline",
        type=str,
        required=True,
        help="Path to baseline_stats.json"
    )
    parser.add_argument(
        "--current",
        type=str,
        required=True,
        help="Path to current_features.jsonl"
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.25,
        help="PSI threshold for CRITICAL status (default: 0.25)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr"
    )
    
    args = parser.parse_args()
    
    # Load baseline stats
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"Error: Baseline file not found: {baseline_path}", file=sys.stderr)
        sys.exit(1)
    
    baseline_stats = load_baseline(baseline_path)
    
    if args.verbose:
        monitored = baseline_stats.get("monitored_features", [])
        print(f"Loaded baseline with {len(monitored)} monitored features", file=sys.stderr)
    
    # Load current features
    current_path = Path(args.current)
    if not current_path.exists():
        print(f"Error: Current features file not found: {current_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(current_path, "r") as f:
        current_features = stream_features(f)
    
    if not current_features:
        print("Error: No features found in current batch", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Loaded {len(current_features)} feature rows from current batch", file=sys.stderr)
    
    # Analyze drift (pure logic)
    results, global_status = analyze_drift(
        baseline_stats, 
        current_features, 
        threshold=args.threshold
    )
    
    # Format output
    output = format_output(results, global_status, args.threshold)
    
    # Write result
    out_path = Path(args.out)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    
    if args.verbose:
        print(f"Wrote drift report to {out_path}", file=sys.stderr)
        print(f"Global status: {global_status}", file=sys.stderr)
        for name, result in results.items():
            print(f"  {name}: PSI={result.psi:.4f}", file=sys.stderr)
    
    # Print JSON summary to stdout (contract requirement)
    print(json.dumps(output))


if __name__ == "__main__":
    main()
