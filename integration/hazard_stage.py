"""integration/hazard_stage.py

Pipeline stage for computing hazard scores from token and wallet features.

This stage is optional and activated via `--enable-hazard-model` flag.
When disabled, all hazard_score values are 0.0.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.survival_model import (
    load_fixed_coefficients,
    predict_exit_hazard,
    REJECT_HAZARD_FEATURES_INVALID,
)

# Default hazard threshold for triggering aggressive exits
DEFAULT_HAZARD_THRESHOLD = 0.35


@dataclass
class HazardMetrics:
    """Metrics for hazard stage execution."""
    hazard_score_avg: float = 0.0
    hazard_score_max: float = 0.0
    hazard_triggered_count: int = 0
    invalid_features_count: int = 0
    total_records: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hazard_score_avg": round(self.hazard_score_avg, 4),
            "hazard_score_max": round(self.hazard_score_max, 4),
            "hazard_triggered_count": self.hazard_triggered_count,
            "invalid_features_count": self.invalid_features_count,
            "total_records": self.total_records,
        }


@dataclass
class HazardStageConfig:
    """Configuration for hazard stage."""
    enabled: bool = False
    hazard_threshold: float = DEFAULT_HAZARD_THRESHOLD
    coefficients_path: Optional[str] = None


class HazardStage:
    """Pipeline stage for computing hazard scores."""
    
    def __init__(self, config: Optional[HazardStageConfig] = None):
        """Initialize hazard stage.
        
        Args:
            config: Optional configuration. If None, uses defaults.
        """
        self.config = config or HazardStageConfig()
        self.coefficients = None
        if self.config.enabled:
            try:
                self.coefficients = load_fixed_coefficients(self.config.coefficients_path)
            except (FileNotFoundError, ValueError) as e:
                print(f"[hazard_stage] WARNING: Could not load coefficients: {e}", file=sys.stderr)
    
    def process_record(
        self,
        token_snapshot: Dict[str, Any],
        wallet_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a single record and compute hazard score.
        
        Args:
            token_snapshot: Token snapshot data.
            wallet_profile: Optional wallet profile data.
        
        Returns:
            Extended record with hazard_score added.
        """
        # If disabled, return with hazard_score = 0.0
        if not self.config.enabled:
            return {
                **token_snapshot,
                "hazard_score": 0.0,
                "hazard_triggered": False,
            }
        
        # Extract features from token_snapshot
        features = self._extract_features(token_snapshot, wallet_profile)
        
        # Compute hazard score
        hazard_score, error = predict_exit_hazard(features, self.coefficients)
        
        # Determine if triggered
        triggered = hazard_score > self.config.hazard_threshold
        
        return {
            **token_snapshot,
            "hazard_score": hazard_score,
            "hazard_triggered": triggered,
            "hazard_error": error,
        }
    
    def _extract_features(
        self,
        token_snapshot: Dict[str, Any],
        wallet_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract hazard features from token and wallet data.
        
        Args:
            token_snapshot: Token snapshot with market data.
            wallet_profile: Wallet profile with trading history.
        
        Returns:
            Dictionary with required features.
        """
        # Extract from token snapshot
        volume_spike = token_snapshot.get("volume_spike_15s_z", 0.0)
        liquidity_drain = token_snapshot.get("liquidity_drain_60s_pct", 0.0)
        price_impact = token_snapshot.get("price_impact_15s_bps", 0.0)
        
        # Extract from wallet profile (smart money exits)
        smart_money_exits = 0
        if wallet_profile:
            # Look for recent exits in wallet history
            wallet_exits = wallet_profile.get("recent_exits_30s", 0)
            tier1_exits = wallet_profile.get("tier1_exits_30s", 0)
            smart_money_exits = tier1_exits or wallet_exits
        
        return {
            "volume_spike_15s_z": volume_spike,
            "smart_money_exits_30s": smart_money_exits,
            "liquidity_drain_60s_pct": liquidity_drain,
            "price_impact_15s_bps": price_impact,
        }
    
    def process_batch(
        self,
        records: List[Dict[str, Any]],
        reject_writer: Optional[Any] = None
    ) -> Tuple[List[Dict[str, Any]], HazardMetrics]:
        """Process a batch of records.
        
        Args:
            records: List of token snapshot records.
            reject_writer: Optional writer for rejected records.
        
        Returns:
            Tuple of (processed_records, metrics).
        """
        metrics = HazardMetrics()
        processed = []
        
        for record in records:
            # Extract wallet profile if present
            wallet_profile = record.pop("wallet_profile", None)
            
            # Process record
            result = self.process_record(record, wallet_profile)
            processed.append(result)
            
            # Update metrics
            metrics.total_records += 1
            hazard_score = result.get("hazard_score", 0.0)
            metrics.hazard_score_avg = (
                (metrics.hazard_score_avg * (metrics.total_records - 1) + hazard_score)
                / metrics.total_records
            )
            metrics.hazard_score_max = max(metrics.hazard_score_max, hazard_score)
            
            if result.get("hazard_triggered", False):
                metrics.hazard_triggered_count += 1
            
            # Track invalid features
            if result.get("hazard_error") and "out of range" in str(result.get("hazard_error", "")):
                metrics.invalid_features_count += 1
                
                # Write to rejects if writer provided
                if reject_writer:
                    reject_writer.write({
                        "reason": "hazard_features_invalid",
                        "details": result,
                    })
        
        return processed, metrics


def run_hazard_stage(
    input_path: str,
    output_path: str,
    enabled: bool = False,
    hazard_threshold: float = DEFAULT_HAZARD_THRESHOLD,
    summary_json: bool = False,
    rejects_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run hazard stage on input file.
    
    Args:
        input_path: Path to input JSONL file.
        output_path: Path to output JSONL file.
        enabled: Whether hazard model is enabled.
        hazard_threshold: Threshold for triggering aggressive exit.
        summary_json: Whether to output summary as JSON.
        rejects_path: Optional path for rejected records.
    
    Returns:
        Summary metrics dict.
    """
    # Load input records
    with open(input_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    
    # Configure stage
    config = HazardStageConfig(
        enabled=enabled,
        hazard_threshold=hazard_threshold,
    )
    stage = HazardStage(config)
    
    # Setup reject writer
    reject_writer = None
    if rejects_path:
        reject_writer = _JsonlWriter(rejects_path)
    
    # Process batch
    processed, metrics = stage.process_batch(records, reject_writer)
    
    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for record in processed:
            f.write(json.dumps(record) + "\n")
    
    # Close reject writer
    if reject_writer:
        reject_writer.close()
    
    result = metrics.to_dict()
    if summary_json:
        print(json.dumps(result))
    
    return result


class _JsonlWriter:
    """Simple JSONL file writer."""
    
    def __init__(self, path: str):
        self.path = path
        self.file = open(path, "w", encoding="utf-8")
    
    def write(self, obj: Any):
        self.file.write(json.dumps(obj) + "\n")
    
    def close(self):
        self.file.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Hazard prediction pipeline stage")
    parser.add_argument("--input", required=True, help="Input JSONL file")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument("--enable-hazard-model", action="store_true", help="Enable hazard model")
    parser.add_argument("--hazard-threshold", type=float, default=DEFAULT_HAZARD_THRESHOLD, 
                        help="Hazard threshold for triggering (default: 0.35)")
    parser.add_argument("--summary-json", action="store_true", help="Output summary as JSON")
    parser.add_argument("--rejects", help="Optional path for rejected records")
    
    args = parser.parse_args()
    
    run_hazard_stage(
        input_path=args.input,
        output_path=args.output,
        enabled=args.enable_hazard_model,
        hazard_threshold=args.hazard_threshold,
        summary_json=args.summary_json,
        rejects_path=args.rejects,
    )
