"""ingestion/pipelines/regime_pipeline.py

PR-PM.2 Risk Regime Pipeline - Orchestrator.

Loads polymarket_snapshots.parquet, computes risk_regime via analysis/risk_regime.py,
and exports to regime_timeline.parquet.

CLI interface:
    python3 -m ingestion.pipelines.regime_pipeline \
        --input polymarket_snapshots.parquet \
        --output regime_timeline.parquet \
        --ts-override=1738945200000 \
        --dry-run \
        --summary-json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from analysis.risk_regime import (
    PolymarketSnapshot,
    RegimeTimeline,
    compute_risk_regime,
    validate_regime_output,
)


def load_snapshots_from_parquet(input_path: str) -> List[PolymarketSnapshot]:
    """Load Polymarket snapshots from parquet file.

    Args:
        input_path: Path to polymarket_snapshots.parquet

    Returns:
        List of PolymarketSnapshot objects
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        # Fallback for testing without pyarrow
        return []

    table = pq.read_table(input_path)
    snapshots: List[PolymarketSnapshot] = []

    for row in table.to_pydict().values():
        # Handle empty or None values
        market_id = str(row.get('market_id', ''))
        question = str(row.get('question', ''))
        p_yes = float(row.get('p_yes', 0.5))
        volume_usd = float(row.get('volume_usd', 0))
        category = str(row.get('category', 'unknown'))

        snapshots.append(PolymarketSnapshot(
            market_id=market_id,
            question=question,
            p_yes=p_yes,
            volume_usd=volume_usd,
            category=category,
        ))

    return snapshots


def load_snapshots_from_json(input_path: str) -> List[PolymarketSnapshot]:
    """Load Polymarket snapshots from JSON/JSONL file (for testing).

    Args:
        input_path: Path to JSON or JSONL file

    Returns:
        List of PolymarketSnapshot objects
    """
    import json

    snapshots: List[PolymarketSnapshot] = []
    path = Path(input_path)

    if path.suffix == '.jsonl':
        with open(input_path, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    snapshots.append(PolymarketSnapshot(
                        market_id=data.get('market_id', ''),
                        question=data.get('question', ''),
                        p_yes=float(data.get('p_yes', 0.5)),
                        volume_usd=float(data.get('volume_usd', 0)),
                        category=data.get('category', 'unknown'),
                    ))
    else:
        with open(input_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    snapshots.append(PolymarketSnapshot(
                        market_id=item.get('market_id', ''),
                        question=item.get('question', ''),
                        p_yes=float(item.get('p_yes', 0.5)),
                        volume_usd=float(item.get('volume_usd', 0)),
                        category=item.get('category', 'unknown'),
                    ))
            else:
                # Single object
                snapshots.append(PolymarketSnapshot(
                    market_id=data.get('market_id', ''),
                    question=data.get('question', ''),
                    p_yes=float(data.get('p_yes', 0.5)),
                    volume_usd=float(data.get('volume_usd', 0)),
                    category=data.get('category', 'unknown'),
                ))

    return snapshots


def save_regime_to_parquet(regime: RegimeTimeline, output_path: str) -> None:
    """Save RegimeTimeline to parquet file.

    Args:
        regime: RegimeTimeline object to save
        output_path: Path for output parquet file
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        # Fallback - can't save parquet without pyarrow
        print(f"[regime_pipeline] Warning: pyarrow not available, skipping parquet export", file=sys.stderr)
        return

    # Create schema
    schema = pa.schema([
        ('ts', pa.int64()),
        ('risk_regime', pa.float64()),
        ('bullish_markets', pa.list_(pa.string())),
        ('bearish_markets', pa.list_(pa.string())),
        ('confidence', pa.float64()),
        ('source_snapshot_id', pa.string()),
    ])

    # Create record
    record = {
        'ts': [regime.ts],
        'risk_regime': [regime.risk_regime],
        'bullish_markets': [regime.bullish_markets],
        'bearish_markets': [regime.bearish_markets],
        'confidence': [regime.confidence],
        'source_snapshot_id': [regime.source_snapshot_id],
    }

    table = pa.table(record, schema=schema)
    pq.write_table(table, output_path)


class RiskRegimePipeline:
    """Orchestrator for risk regime computation pipeline."""

    def __init__(self):
        """Initialize pipeline."""
        pass

    def run(
        self,
        input_path: str,
        output_path: str,
        ts_override: Optional[int] = None,
        dry_run: bool = False,
        summary_json: bool = False,
    ) -> Dict[str, Any]:
        """Execute the risk regime pipeline.

        Args:
            input_path: Path to input polymarket_snapshots.parquet
            output_path: Path for output regime_timeline.parquet
            ts_override: Optional timestamp override (Unix ms)
            dry_run: If True, don't write output files
            summary_json: If True, print JSON summary to stdout

        Returns:
            Dictionary with pipeline results
        """
        # Determine ts
        if ts_override is not None:
            ts = ts_override
        else:
            # Use current time in milliseconds
            ts = int(datetime.utcnow().timestamp() * 1000)

        # Generate snapshot_id from input path and ts
        snapshot_id = f"{Path(input_path).stem}_{ts}"

        # Load snapshots
        print(f"[regime_pipeline] Loading snapshots from {input_path}...", file=sys.stderr)

        if input_path.endswith('.parquet'):
            snapshots = load_snapshots_from_parquet(input_path)
        else:
            snapshots = load_snapshots_from_json(input_path)

        print(f"[regime_pipeline] Loaded {len(snapshots)} snapshots", file=sys.stderr)

        if not snapshots:
            print("[regime_pipeline] Warning: No snapshots loaded, using neutral regime", file=sys.stderr)

        # Compute regime
        print(f"[regime_pipeline] Computing risk regime...", file=sys.stderr)
        regime = compute_risk_regime(snapshots, ts, snapshot_id)

        # Validate output range
        validate_regime_output(regime)

        print(
            f"[regime_pipeline] computed risk_regime={regime.risk_regime:+.2f} "
            f"(bullish:{len(regime.bullish_markets)}, bearish:{len(regime.bearish_markets)})",
            file=sys.stderr
        )

        # Save output (unless dry_run)
        if not dry_run:
            print(f"[regime_pipeline] Saving to {output_path}...", file=sys.stderr)
            save_regime_to_parquet(regime, output_path)

        # Prepare result
        result = {
            "ts": regime.ts,
            "risk_regime": regime.risk_regime,
            "bullish_count": len(regime.bullish_markets),
            "bearish_count": len(regime.bearish_markets),
            "confidence": regime.confidence,
            "schema_version": "regime_timeline.v1",
        }

        # Print summary JSON to stdout if requested
        if summary_json:
            print(json.dumps(result))

        return result


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(
        description="Risk Regime Pipeline - Compute risk_regime from Polymarket snapshots"
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Input path (polymarket_snapshots.parquet or JSON/JSONL)",
    )
    ap.add_argument(
        "--output",
        default="regime_timeline.parquet",
        help="Output path for regime_timeline.parquet",
    )
    ap.add_argument(
        "--ts-override",
        type=int,
        default=None,
        help="Unix timestamp in milliseconds (default: current time)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Compute regime without writing output files",
    )
    ap.add_argument(
        "--summary-json",
        action="store_true",
        default=False,
        help="Print summary JSON to stdout",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging",
    )

    args = ap.parse_args()

    pipeline = RiskRegimePipeline()
    result = pipeline.run(
        input_path=args.input,
        output_path=args.output,
        ts_override=args.ts_override,
        dry_run=args.dry_run,
        summary_json=args.summary_json,
    )

    if args.verbose:
        print(f"[regime_pipeline] Result: {json.dumps(result, indent=2)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
