#!/usr/bin/env python3
"""integration/ml_retraining_check.py

PR-N.2 ML Retraining Trigger CLI

CLI tool wrapping the pure retraining decision logic.
Prints exactly one JSON line with the decision to stdout.
All logs go to stderr.

Usage:
    python -m integration.ml_retraining_check \
        --metadata <json_path> \
        --current <jsonl_path> \
        --config <yaml_path> \
        --now <timestamp>

Args:
    --metadata: Path to JSON file with last_train_ts and baseline_stats
    --current: Path to JSONL file with current feature vectors
    --config: Path to YAML file with thresholds (cadence_hours, drift_psi_threshold)
    --now: Optional Unix timestamp for current time (defaults to now)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_metadata(path: str) -> Dict[str, Any]:
    """Load model metadata from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_current_features(path: str) -> Dict[str, List[float]]:
    """Load current feature vectors from JSONL file.
    
    Returns:
        Dict mapping feature names to lists of values
    """
    features: Dict[str, List[float]] = {}
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            record = json.loads(line)
            for key, value in record.items():
                if key not in features:
                    features[key] = []
                # Handle both scalar and list values
                if isinstance(value, list):
                    features[key].extend(value)
                else:
                    features[key].append(value)
    
    return features


def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_baseline_from_metadata(metadata: Dict[str, Any]) -> Dict[str, List[float]]:
    """Extract baseline statistics from metadata."""
    return metadata.get("baseline_stats", {})


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ML Retraining Trigger Check"
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="Path to JSON file with model metadata"
    )
    parser.add_argument(
        "--current",
        required=True,
        help="Path to JSONL file with current feature vectors"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML configuration file"
    )
    parser.add_argument(
        "--now",
        type=int,
        default=None,
        help="Optional Unix timestamp for current time"
    )
    
    args = parser.parse_args()
    
    # Load inputs
    try:
        metadata = load_metadata(args.metadata)
        current_features = load_current_features(args.current)
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML: {e}", file=sys.stderr)
        return 1
    
    # Set current timestamp
    if args.now is not None:
        metadata["current_ts"] = args.now
    else:
        metadata["current_ts"] = int(__import__("time").time())
    
    # Get config section
    retraining_config = config.get("retraining", config)
    
    # Import pure logic
    from strategy.ml_trigger import decide_retraining
    
    # Run decision logic
    result = decide_retraining(
        metadata=metadata,
        current_features=current_features,
        config=retraining_config,
    )
    
    # Print result to stdout (single JSON line)
    print(json.dumps(result))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
