#!/usr/bin/env python3
# integration/tools/export_grafana.py
# CLI adapter transforming input files to InfluxDB Line Protocol format on stdout.
# Uses influx_line_protocol functions from monitoring_fmt module.

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from strategy.monitoring_fmt import (
    convert_metrics_to_influx,
    convert_signals_to_influx,
    flatten_metrics,
    influx_line_protocol,  # Alias for backwards compatibility
    to_influx_line,
)


def load_json(file_path: str) -> Dict:
    """Load JSON file and return dict."""
    with open(file_path, "r") as f:
        return json.load(f)


def load_jsonl(file_path: str) -> List[Dict]:
    """Load JSONL file and return list of dicts."""
    records = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def process_metrics(
    input_file: str,
    measurement: str,
) -> List[str]:
    """
    Process metrics JSON file and return InfluxDB Line Protocol lines.
    
    Args:
        input_file: Path to metrics JSON file.
        measurement: Measurement name.
        
    Returns:
        List of InfluxDB Line Protocol strings.
    """
    data = load_json(input_file)
    
    # Default tag keys for metrics
    tag_keys = ["mode", "version"]
    
    # Filter to only include keys that exist in data
    available_tag_keys = [k for k in tag_keys if k in data]
    
    # Extract timestamp if present
    timestamp_ns = None
    if "timestamp" in data:
        ts_val = data["timestamp"]
        if isinstance(ts_val, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                timestamp_ns = int(dt.timestamp() * 1e9)
            except ValueError:
                pass
        elif isinstance(ts_val, (int, float)):
            timestamp_ns = int(ts_val)
    
    # Build tag dict with available tag keys
    tags = {}
    for key in available_tag_keys:
        value = data[key]
        if isinstance(value, str):
            tags[key] = value
        else:
            tags[key] = str(value)
    
    # Build fields dict with all other keys
    fields = {}
    for key, value in data.items():
        if key in ("timestamp",):
            continue
        if key not in available_tag_keys:
            fields[key] = value
    
    # Flatten nested structures
    if fields:
        fields = flatten_metrics(fields)
    
    line = to_influx_line(measurement, tags, fields, timestamp_ns)
    
    return [line] if line else []


def process_signals(
    input_file: str,
    measurement: str,
) -> List[str]:
    """
    Process signals JSONL file and return InfluxDB Line Protocol lines.
    
    Args:
        input_file: Path to signals JSONL file.
        measurement: Measurement name.
        
    Returns:
        List of InfluxDB Line Protocol strings.
    """
    signals = load_jsonl(input_file)
    
    lines = convert_signals_to_influx(
        signals=signals,
        measurement=measurement,
        timestamp_key="ts",
    )
    
    return lines


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export strategy artifacts to InfluxDB Line Protocol"
    )
    parser.add_argument(
        "--input", required=True, help="Path to input file (JSON or JSONL)"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["metrics", "signals"],
        help="Type of input file",
    )
    parser.add_argument(
        "--measurement",
        default="strategy_metrics",
        help="Measurement name (default: strategy_metrics for metrics, signals for signals)",
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Determine measurement name
    measurement = args.measurement
    if args.type == "signals" and measurement == "strategy_metrics":
        measurement = "signals"
    
    # Process based on type
    lines = []
    try:
        if args.type == "metrics":
            lines = process_metrics(args.input, measurement)
        else:
            lines = process_signals(args.input, measurement)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Output lines to stdout (one per line)
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
