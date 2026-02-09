#!/usr/bin/env python3
"""
Trade Forensics Pipeline Stage.

Aggregates signals, features, and execution data into unified forensics bundles.
Outputs trade_forensics.v1.jsonl format.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, TextIO

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.forensics.assembler import assemble_forensics


def parse_jsonl(file_handle: TextIO) -> Dict[str, dict]:
    result = {}
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        doc_id = doc.get("signal_id", doc.get("id", ""))
        if doc_id:
            result[doc_id] = doc
    return result


def load_jsonl(file_path: Path) -> Dict[str, dict]:
    if not file_path.exists():
        return {}
    with open(file_path, "r") as f:
        return parse_jsonl(f)


def run_forensics_stage(
    signals_path: Path,
    features_path: Path,
    execution_path: Path,
    out_path: Path,
    verbose: bool = False,
) -> dict:
    start_time = time.time()
    
    signals = load_jsonl(signals_path)
    features_map = load_jsonl(features_path)
    execution_map = load_jsonl(execution_path)
    
    matched_count = 0
    orphaned_signals = 0
    
    with open(out_path, "w") as out_file:
        for signal_id, signal in signals.items():
            features = features_map.get(signal_id)
            execution = execution_map.get(signal_id)
            
            if features:
                matched_count += 1
            else:
                orphaned_signals += 1
            
            bundle = assemble_forensics(signal, features, execution)
            out_file.write(json.dumps(bundle) + "\n")
    
    elapsed = time.time() - start_time
    
    metrics = {
        "total_signals": len(signals),
        "matched_count": matched_count,
        "orphaned_signals": orphaned_signals,
        "elapsed_sec": round(elapsed, 2),
    }
    
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Trade Forensics Pipeline Stage")
    parser.add_argument("--signals", type=str, required=True)
    parser.add_argument("--features", type=str, required=True)
    parser.add_argument("--execution", type=str, required=True)
    parser.add_argument("--out", type=str, required=True)
    parser.add_argument("--verbose", action="store_true")
    
    args = parser.parse_args()
    
    signals_path = Path(args.signals)
    features_path = Path(args.features)
    execution_path = Path(args.execution)
    out_path = Path(args.out)
    
    for name, path in [("signals", signals_path), ("features", features_path)]:
        if not path.exists():
            print(f"Error: {name} file not found: {path}", file=sys.stderr)
            return 1
    
    metrics = run_forensics_stage(signals_path, features_path, execution_path, out_path, args.verbose)
    
    if args.verbose:
        for key, value in metrics.items():
            print(f"[forensics_stage] {key}: {value}", file=sys.stderr)
    
    print(json.dumps(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
