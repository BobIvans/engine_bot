#!/usr/bin/env python3
"""
Flipside Historical Backfill Stage (PR-Y.3).

Optional stage for loading and normalizing trade data from Flipside Crypto.
Activated via --use-flipside flag, otherwise acts as no-op.

Usage:
    python -m integration.flipside_ingestion --use-flipside --source <file> --out <file>
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, TextIO, Tuple

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy.ingestion import normalize_flipside_trade, TradeEvent
from strategy.ingestion import (
    FLIPSIDE_REJECT_SCHEMA_MISMATCH,
    FLIPSIDE_REJECT_MISSING_FIELD,
    FLIPSIDE_REJECT_INVALID_PROGRAM_ID,
)


def parse_jsonl(file_handle: TextIO) -> List[dict]:
    """Parse JSONL file into list of dictionaries."""
    result = []
    for line in file_handle:
        line = line.strip()
        if not line:
            continue
        result.append(json.loads(line))
    return result


def run_flipside_stage(
    source_path: Path,
    out_path: Path,
    rejects_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Run Flipside ingestion stage.
    
    Args:
        source_path: Path to Flipside data file (JSONL)
        out_path: Path for normalized output (JSONL)
        rejects_path: Path for rejected trades (JSONL)
        verbose: Enable verbose logging
        
    Returns:
        Dict with metrics (flipside_total, flipside_accepted, flipside_rejected)
    """
    start_time = time.time()
    
    # Load source data
    with open(source_path, "r") as f:
        rows = parse_jsonl(f)
    
    total_count = len(rows)
    accepted_count = 0
    rejected_count = 0
    
    # Process each row
    with open(out_path, "w") as out_file:
        with open(rejects_path, "w") as rejects_file:
            for row in rows:
                event, reject_reason = normalize_flipside_trade(row)
                
                if event:
                    # Success - write normalized event
                    out_file.write(json.dumps(event.to_dict()) + "\n")
                    accepted_count += 1
                else:
                    # Failure - write rejection (use the reason from pure logic)
                    rejected_count += 1
                    
                    reject_record = {
                        "signal_id": f"flipside_{row.get('tx_hash', 'unknown')}",
                        "mint": row.get("token_mint", "unknown"),
                        "wallet": row.get("swapper", "unknown"),
                        "reason": reject_reason,
                        "timestamp": int(time.time()),
                        "raw_data": row,
                    }
                    rejects_file.write(json.dumps(reject_record) + "\n")
    
    elapsed = time.time() - start_time
    
    metrics = {
        "flipside_total": total_count,
        "flipside_accepted": accepted_count,
        "flipside_rejected": rejected_count,
        "elapsed_sec": round(elapsed, 2),
    }
    
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Flipside Historical Backfill Stage"
    )
    parser.add_argument(
        "--use-flipside",
        action="store_true",
        help="Activate Flipside ingestion (required to run)"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Path to Flipside data file (JSONL)"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Path for normalized output (JSONL)"
    )
    parser.add_argument(
        "--rejects",
        type=str,
        help="Path for rejected trades (JSONL)"
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output metrics as JSON to stdout"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Check if stage is activated
    if not args.use_flipside:
        # No-op mode - just output empty metrics
        print(json.dumps({"flipside_total": 0, "flipside_accepted": 0, "flipside_rejected": 0}))
        return 0
    
    # Validate required arguments when activated
    if not args.source or not args.out or not args.rejects:
        print("Error: --source, --out, and --rejects are required when --use-flipside is set", file=sys.stderr)
        return 1
    
    # Validate source file
    source_path = Path(args.source)
    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}", file=sys.stderr)
        return 1
    
    # Run stage
    metrics = run_flipside_stage(
        source_path=source_path,
        out_path=Path(args.out),
        rejects_path=Path(args.rejects),
        verbose=args.verbose,
    )
    
    # Output
    if args.summary_json:
        print(json.dumps(metrics))
    else:
        # Write metrics to stderr
        for key, value in metrics.items():
            print(f"[flipside_ingestion] {key}: {value}", file=sys.stderr)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
