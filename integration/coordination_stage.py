"""integration/coordination_stage.py

PR-Z.5 Multi-Wallet Coordination Detector.

Pipeline stage for detecting coordinated trading patterns on a sliding window (60s).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from strategy.coordinated_actions import (
    CoordinationTrade,
    detect_coordination,
    REJECT_COORDINATION_INVALID_INPUT,
)


@dataclass
class CoordinationResult:
    """Result of coordination detection for a single trade."""
    wallet: str
    coordination_score: float


@dataclass
class CoordinationStage:
    """Sliding window coordination detection stage.
    
    Maintains a buffer of trades within the window and computes
    coordination scores for each wallet.
    """
    window_sec: float = 60.0
    enabled: bool = False
    coordination_threshold: float = 0.7
    
    # Internal state
    _buffer: List[CoordinationTrade] = field(default_factory=list, repr=False)
    
    def add_trade(self, trade: CoordinationTrade) -> Optional[CoordinationResult]:
        """Add a trade to the buffer and return coordination result.
        
        Args:
            trade: Trade to analyze.
            
        Returns:
            CoordinationResult with score, or None if disabled.
        """
        if not self.enabled:
            return None
        
        # Add to buffer
        self._buffer.append(trade)
        
        # Remove trades outside window
        max_ts = trade["ts_block"]
        self._buffer = [
            t for t in self._buffer
            if max_ts - t["ts_block"] <= self.window_sec
        ]
        
        try:
            # Detect coordination
            scores = detect_coordination(self._buffer, self.window_sec)
            
            wallet = trade["wallet"]
            score = scores.get(wallet, 0.0)
            
            return CoordinationResult(wallet=wallet, coordination_score=score)
            
        except ValueError:
            # Invalid input - log warning and return base score
            print(f"[coordination_stage] WARNING: Invalid input for {trade.get('wallet', 'unknown')}", file=sys.stderr)
            return CoordinationResult(wallet=trade["wallet"], coordination_score=0.0)
    
    def compute_metrics(self) -> Dict[str, Any]:
        """Compute summary metrics for the entire window.
        
        Returns:
            Dictionary with coordination metrics.
        """
        if not self.enabled or not self._buffer:
            return {
                "coordination_score_avg": 0.0,
                "coordination_score_max": 0.0,
                "coordination_high_count": 0,
            }
        
        try:
            scores = detect_coordination(self._buffer, self.window_sec)
            
            if not scores:
                return {
                    "coordination_score_avg": 0.0,
                    "coordination_score_max": 0.0,
                    "coordination_high_count": 0,
                }
            
            values = list(scores.values())
            avg_score = sum(values) / len(values)
            max_score = max(values)
            high_count = sum(1 for v in values if v > self.coordination_threshold)
            
            return {
                "coordination_score_avg": avg_score,
                "coordination_score_max": max_score,
                "coordination_high_count": high_count,
            }
            
        except ValueError:
            return {
                "coordination_score_avg": 0.0,
                "coordination_score_max": 0.0,
                "coordination_high_count": 0,
            }
    
    def reset(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()


def run_coordination_stage(
    input_path: str,
    enabled: bool = False,
    coordination_threshold: float = 0.7,
    window_sec: float = 60.0,
) -> Dict[str, Any]:
    """Run coordination detection on a JSONL file.
    
    Args:
        input_path: Path to input JSONL file with trades.
        enabled: Whether coordination detection is enabled.
        coordination_threshold: Threshold for high coordination score.
        window_sec: Sliding window size in seconds.
        
    Returns:
        Dictionary with coordination metrics.
    """
    stage = CoordinationStage(
        window_sec=window_sec,
        enabled=enabled,
        coordination_threshold=coordination_threshold,
    )
    
    # Process trades
    with open(input_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                trade = json.loads(line)
                
                # Convert to CoordinationTrade format
                coord_trade: CoordinationTrade = {
                    "ts_block": float(trade["ts_block"]),
                    "wallet": str(trade["wallet"]),
                    "mint": str(trade["mint"]),
                    "side": str(trade["side"]),
                    "size": float(trade["size"]),
                    "price": float(trade["price"]),
                }
                
                stage.add_trade(coord_trade)
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"[coordination_stage] ERROR: Failed to parse line: {e}", file=sys.stderr)
                continue
    
    # Get final metrics
    metrics = stage.compute_metrics()
    
    return metrics
