"""
PR-PM.3 Event Risk Pipeline

Pipeline orchestrator for event risk detection from Polymarket snapshots.
Connects snapshot ingestion, event type detection, and risk aggregation.
"""

import json
import time
from pathlib import Path
from typing import List, Optional

from analysis.event_risk import (
    detect_event_risk,
    detect_event_type,
    compute_days_to_resolution,
    EventRiskTimeline,
    PolymarketSnapshotInput,
)


def load_polymarket_snapshots(snapshot_path: str) -> List[PolymarketSnapshotInput]:
    """
    Load Polymarket snapshots from JSON file.
    
    Args:
        snapshot_path: Path to JSON file with snapshot data
        
    Returns:
        List of PolymarketSnapshotInput objects
    """
    with open(snapshot_path, 'r') as f:
        data = json.load(f)
    
    snapshots = []
    for item in data:
        snapshots.append(PolymarketSnapshotInput(
            market_id=item.get('market_id', ''),
            question=item.get('question', ''),
            event_date=item.get('event_date', 0),
        ))
    
    return snapshots


def save_event_risk_timeline(
    timeline: EventRiskTimeline,
    output_path: str,
    pretty: bool = True
) -> None:
    """
    Save event risk timeline to JSON file.
    
    Args:
        timeline: EventRiskTimeline to save
        output_path: Path to output JSON file
        pretty: Whether to pretty-print JSON
    """
    data = {
        'ts': timeline.ts,
        'high_event_risk': timeline.high_event_risk,
        'days_to_resolution': timeline.days_to_resolution,
        'event_type': timeline.event_type,
        'event_name': timeline.event_name,
        'source_snapshot_id': timeline.source_snapshot_id,
    }
    
    with open(output_path, 'w') as f:
        if pretty:
            json.dump(data, f, indent=2)
        else:
            json.dump(data, f)


class EventRiskPipeline:
    """
    Pipeline orchestrator for event risk detection.
    """
    
    def __init__(
        self,
        snapshot_path: str,
        output_path: str,
        now_ts_ms: Optional[int] = None,
        skip_event_risk: bool = False,
    ):
        """
        Initialize the event risk pipeline.
        
        Args:
            snapshot_path: Path to Polymarket snapshots JSON
            output_path: Path for output timeline JSON
            now_ts_ms: Reference timestamp (default: current time)
            skip_event_risk: Skip event risk processing flag
        """
        self.snapshot_path = snapshot_path
        self.output_path = output_path
        self.now_ts_ms = now_ts_ms or int(time.time() * 1000)
        self.skip_event_risk = skip_event_risk
        
    def run(self) -> EventRiskTimeline:
        """
        Execute the event risk pipeline.
        
        Returns:
            EventRiskTimeline with aggregated results
        """
        if self.skip_event_risk:
            # Return empty/default timeline when skipped
            return EventRiskTimeline(
                ts=self.now_ts_ms,
                high_event_risk=False,
                days_to_resolution=0,
                event_type="other",
                event_name="",
                source_snapshot_id="",
            )
        
        # Load snapshots
        snapshots = load_polymarket_snapshots(self.snapshot_path)
        
        # Detect and aggregate event risk
        timeline = detect_event_risk(snapshots, self.now_ts_ms)
        
        # Save output
        save_event_risk_timeline(timeline, self.output_path)
        
        return timeline


def main():
    """CLI entry point for event risk pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(description='PR-PM.3 Event Risk Pipeline')
    parser.add_argument('--snapshot-path', required=True, help='Path to Polymarket snapshots JSON')
    parser.add_argument('--output-path', required=True, help='Path for output timeline JSON')
    parser.add_argument('--now-ts-ms', type=int, help='Reference timestamp in milliseconds')
    parser.add_argument('--skip-event-risk', action='store_true', help='Skip event risk processing')
    
    args = parser.parse_args()
    
    pipeline = EventRiskPipeline(
        snapshot_path=args.snapshot_path,
        output_path=args.output_path,
        now_ts_ms=args.now_ts_ms,
        skip_event_risk=args.skip_event_risk,
    )
    
    timeline = pipeline.run()
    print(f"Event risk detected: high_risk={timeline.high_event_risk}, "
          f"days={timeline.days_to_resolution}, type={timeline.event_type}")


if __name__ == '__main__':
    main()
