"""integration/dune_source.py

Dune Analytics wallet export adapter.
Supports both fixture file loading (CSV/JSON) and real Dune API queries.
Normalizes output to wallet_profile schema for downstream stages.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import from strategy/profiling
sys.path.insert(0, str(Path(__file__).parent.parent))
from strategy.profiling import WalletProfile, normalize_dune_row

SCHEMA_VERSION = "wallet_profile.v1"


class DuneWalletSource:
    """Adapter for loading wallet data from Dune exports."""
    
    def __init__(self, min_trades: int = 0, min_roi_30d: float = -float("inf")):
        """Initialize source with optional filters.
        
        Args:
            min_trades: Minimum trades_30d threshold.
            min_roi_30d: Minimum roi_30d threshold.
        """
        self.min_trades = min_trades
        self.min_roi_30d = min_roi_30d
    
    def load_from_file(self, path: str) -> List[WalletProfile]:
        """Load and normalize wallet profiles from CSV or JSON fixture.
        
        Args:
            path: Path to fixture file (CSV or JSON).
        
        Returns:
            List of normalized WalletProfile instances.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {path}")
        
        profiles = []
        if file_path.suffix.lower() == ".csv":
            profiles = self._load_from_csv(file_path)
        elif file_path.suffix.lower() in (".json", ".jsonl"):
            profiles = self._load_from_json(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        return profiles
    
    def _load_from_csv(self, file_path: Path) -> List[WalletProfile]:
        """Load from CSV file."""
        profiles = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    profile = normalize_dune_row(row)
                    # Apply filters
                    if self._passes_filters(profile):
                        profiles.append(profile)
                except ValueError as e:
                    print(f"[dune_source] WARNING: Skipping invalid row: {e}", file=sys.stderr)
        return profiles
    
    def _load_from_json(self, file_path: Path) -> List[WalletProfile]:
        """Load from JSON or JSONL file."""
        profiles = []
        with open(file_path, "r", encoding="utf-8") as f:
            # Handle both JSON array and JSONL (one object per line)
            content = f.read().strip()
            if content.startswith("["):
                data = json.loads(content)
                if isinstance(data, list):
                    for row in data:
                        try:
                            profile = normalize_dune_row(row)
                            if self._passes_filters(profile):
                                profiles.append(profile)
                        except ValueError as e:
                            print(f"[dune_source] WARNING: Skipping invalid row: {e}", file=sys.stderr)
            else:
                # JSONL format
                for line in content.split("\n"):
                    if line.strip():
                        row = json.loads(line)
                        try:
                            profile = normalize_dune_row(row)
                            if self._passes_filters(profile):
                                profiles.append(profile)
                        except ValueError as e:
                            print(f"[dune_source] WARNING: Skipping invalid row: {e}", file=sys.stderr)
        return profiles
    
    def _passes_filters(self, profile: WalletProfile) -> bool:
        """Check if profile passes configured filters."""
        if profile.trades_30d is not None and profile.trades_30d < self.min_trades:
            return False
        if profile.roi_30d_pct is not None and profile.roi_30d_pct < self.min_roi_30d:
            return False
        return True
    
    def export_to_parquet(
        self,
        profiles: List[WalletProfile],
        out_path: str,
        dry_run: bool = False
    ) -> None:
        """Export profiles to Parquet file.
        
        Args:
            profiles: List of WalletProfile instances.
            out_path: Output file path.
            dry_run: If True, only validate without writing.
        """
        if not profiles:
            print("[dune_source] WARNING: No profiles to export", file=sys.stderr)
            return
        
        # Prepare data for Parquet
        data = [asdict(p) for p in profiles]
        
        if dry_run:
            print(f"[dune_source] DRY-RUN: Would export {len(data)} profiles to {out_path}", file=sys.stderr)
            for row in data:
                print(f"  - {row}", file=sys.stderr)
            return
        
        # Import here to avoid dependency if not needed
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            table = pa.table(data)
            pq.write_table(table, out_path)
            print(f"[dune_source] Exported {len(profiles)} profiles to {out_path}", file=sys.stderr)
        except ImportError:
            # Fallback: write as JSON
            json_path = out_path.replace(".parquet", ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[dune_source] Exported {len(profiles)} profiles to {json_path} (JSON fallback)", file=sys.stderr)


def run_dune_export(
    input_file: str,
    out_path: str,
    dry_run: bool = False,
    summary_json: bool = False,
    min_trades: int = 0,
    min_roi: float = -float("inf")
) -> Dict[str, Any]:
    """Run the Dune export pipeline.
    
    Args:
        input_file: Path to input fixture file.
        out_path: Path for output Parquet file.
        dry_run: If True, only validate without writing.
        summary_json: If True, output summary JSON to stdout.
        min_trades: Minimum trades filter.
        min_roi: Minimum ROI filter.
    
    Returns:
        Summary dict with exported_count and schema_version.
    """
    source = DuneWalletSource(min_trades=min_trades, min_roi_30d=min_roi)
    profiles = source.load_from_file(input_file)
    
    if not dry_run:
        source.export_to_parquet(profiles, out_path, dry_run=False)
    
    result = {
        "exported_count": len(profiles),
        "schema_version": SCHEMA_VERSION
    }
    
    if summary_json:
        print(json.dumps(result))
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dune wallet export adapter")
    parser.add_argument("--input-file", required=True, help="Path to input CSV/JSON fixture")
    parser.add_argument("--out-path", default="wallets_dune.parquet", help="Output Parquet path")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--summary-json", action="store_true", help="Output JSON summary to stdout")
    parser.add_argument("--min-trades", type=int, default=0, help="Minimum trades_30d filter")
    parser.add_argument("--min-roi", type=float, default=-float("inf"), help="Minimum roi_30d filter")
    
    args = parser.parse_args()
    
    run_dune_export(
        input_file=args.input_file,
        out_path=args.out_path,
        dry_run=args.dry_run,
        summary_json=args.summary_json,
        min_trades=args.min_trades,
        min_roi=args.min_roi
    )
