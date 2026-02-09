"""ingestion/pipelines/wallet_cluster_pipeline.py

Pipeline for building wallet co-trade clusters and enriching wallet profiles.

This module orchestrates:
1. Loading normalized trades from Parquet
2. Building co-trade graph via wallet_graph.py
3. Computing cluster metrics (leader_score, follower_lag_ms, etc.)
4. Exporting enriched wallet profiles to Parquet
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.wallet_graph import (
    build_clusters,
    TradeNorm,
    WalletClusterMetrics,
)

# Default values
DEFAULT_MIN_CO_TRADES = 3
DEFAULT_WINDOW_MS = 60_000  # 60 seconds
SCHEMA_VERSION = "wallet_cluster.v1"


class WalletClusterPipeline:
    """Pipeline for wallet co-trade clustering."""
    
    def __init__(
        self,
        min_co_trades: int = DEFAULT_MIN_CO_TRADES,
        window_ms: int = DEFAULT_WINDOW_MS
    ):
        """Initialize pipeline with parameters.
        
        Args:
            min_co_trades: Minimum co-trades to establish cluster connection.
            window_ms: Time window in milliseconds for co-trade detection.
        """
        self.min_co_trades = min_co_trades
        self.window_ms = window_ms
    
    def load_trades(self, input_path: str) -> List[TradeNorm]:
        """Load normalized trades from Parquet or JSONL file.
        
        Args:
            input_path: Path to input file (Parquet or JSONL).
        
        Returns:
            List of TradeNorm records.
        """
        # Check file extension to determine format
        if input_path.endswith('.jsonl'):
            return self._load_trades_jsonl(input_path)
        else:
            return self._load_trades_parquet(input_path)
    
    def _load_trades_jsonl(self, input_path: str) -> List[TradeNorm]:
        """Load trades from JSONL file."""
        records = []
        with open(input_path, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    try:
                        records.append(TradeNorm(
                            wallet_addr=data['wallet_addr'],
                            mint=data['mint'],
                            ts_ms=data['ts_ms'],
                            side=data['side'],
                            size_usd=data['size_usd']
                        ))
                    except (KeyError, ValueError) as e:
                        print(f"[wallet_cluster_pipeline] WARNING: Skipping invalid record: {e}", file=sys.stderr)
                        continue
        return records
    
    def _load_trades_parquet(self, input_path: str) -> List[TradeNorm]:
        """Load trades from Parquet file."""
        try:
            import pyarrow.parquet as pq
            
            table = pq.read_table(input_path)
            records = []
            
            # Convert to dict access
            columns = table.column_names
            for i in range(table.num_rows):
                row_data = {}
                for col in columns:
                    row_data[col] = table.column(col)[i].as_py()
                
                try:
                    records.append(TradeNorm(
                        wallet_addr=str(row_data.get('wallet_addr', '')),
                        mint=str(row_data.get('mint', '')),
                        ts_ms=int(row_data.get('ts_ms', 0)),
                        side=str(row_data.get('side', '')),
                        size_usd=float(row_data.get('size_usd', 0.0))
                    ))
                except (ValueError, TypeError) as e:
                    print(f"[wallet_cluster_pipeline] WARNING: Skipping invalid row: {e}", file=sys.stderr)
                    continue
            
            return records
            
        except ImportError:
            # Fallback: try to read as JSONL even if extension is wrong
            jsonl_path = input_path.replace('.parquet', '.jsonl')
            return self._load_trades_jsonl(jsonl_path)
    
    def export_profiles(
        self,
        metrics: Dict[str, WalletClusterMetrics],
        output_path: str,
        dry_run: bool = False
    ) -> None:
        """Export enriched wallet profiles to Parquet.
        
        Args:
            metrics: Mapping of wallet_addr -> WalletClusterMetrics.
            output_path: Path for output Parquet file.
            dry_run: If True, only validate without writing.
        """
        if dry_run:
            print(f"[wallet_cluster_pipeline] DRY-RUN: Would export {len(metrics)} profiles to {output_path}", file=sys.stderr)
            for wallet, m in metrics.items():
                print(f"  - {wallet}: cluster={m.cluster_label}, leader_score={m.leader_score}", file=sys.stderr)
            return
        
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            # Convert to list of dicts
            data = []
            for wallet, m in metrics.items():
                d = asdict(m)
                # Convert None to appropriate types
                d['cluster_label'] = m.cluster_label
                d['leader_score'] = m.leader_score
                d['follower_lag_ms'] = m.follower_lag_ms
                d['co_trade_count'] = m.co_trade_count
                data.append(d)
            
            if data:
                table = pa.table(data)
                pq.write_table(table, output_path)
                print(f"[wallet_cluster_pipeline] Exported {len(metrics)} profiles to {output_path}", file=sys.stderr)
            else:
                print("[wallet_cluster_pipeline] WARNING: No metrics to export", file=sys.stderr)
                
        except ImportError:
            # Fallback: write as JSON
            json_path = output_path.replace('.parquet', '.json')
            output_data = {wallet: asdict(m) for wallet, m in metrics.items()}
            with open(json_path, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"[wallet_cluster_pipeline] Exported {len(metrics)} profiles to {json_path} (JSON fallback)", file=sys.stderr)
    
    def run(
        self,
        input_path: str,
        output_path: str,
        dry_run: bool = False,
        summary_json: bool = False
    ) -> Dict[str, Any]:
        """Run the wallet clustering pipeline.
        
        Args:
            input_path: Path to input Parquet file.
            output_path: Path for output Parquet file.
            dry_run: If True, only validate without writing.
            summary_json: If True, output summary JSON to stdout.
        
        Returns:
            Summary dict with metrics.
        """
        # Load trades
        trades = self.load_trades(input_path)
        
        # Build clusters
        metrics = build_clusters(
            trades=trades,
            min_co_trades=self.min_co_trades,
            window_ms=self.window_ms
        )
        
        # Export
        self.export_profiles(metrics, output_path, dry_run)
        
        # Compute summary
        cluster_labels = set(m.cluster_label for m in metrics.values() if m.cluster_label is not None)
        
        result = {
            "clusters_count": len(cluster_labels),
            "total_wallets": len(metrics),
            "schema_version": SCHEMA_VERSION
        }
        
        if summary_json:
            print(json.dumps(result))
        
        return result


def run_pipeline(
    input_path: str,
    output_path: str,
    dry_run: bool = False,
    summary_json: bool = False,
    min_co_trades: int = DEFAULT_MIN_CO_TRADES,
    window_ms: int = DEFAULT_WINDOW_MS
) -> Dict[str, Any]:
    """Convenience function to run the clustering pipeline."""
    pipeline = WalletClusterPipeline(
        min_co_trades=min_co_trades,
        window_ms=window_ms
    )
    return pipeline.run(
        input_path=input_path,
        output_path=output_path,
        dry_run=dry_run,
        summary_json=summary_json
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Wallet cluster pipeline")
    parser.add_argument("--input", required=True, help="Input Parquet file")
    parser.add_argument("--output", required=True, help="Output Parquet file")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--summary-json", action="store_true", help="Output summary as JSON")
    parser.add_argument("--min-co-trades", type=int, default=DEFAULT_MIN_CO_TRADES,
                        help="Minimum co-trades for cluster connection")
    parser.add_argument("--window-ms", type=int, default=DEFAULT_WINDOW_MS,
                        help="Time window in ms for co-trade detection")
    
    args = parser.parse_args()
    
    run_pipeline(
        input_path=args.input,
        output_path=args.output,
        dry_run=args.dry_run,
        summary_json=args.summary_json,
        min_co_trades=args.min_co_trades,
        window_ms=args.window_ms
    )
