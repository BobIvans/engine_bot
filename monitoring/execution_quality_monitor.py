"""monitoring/execution_quality_monitor.py

PR-E.6 Execution Quality Monitor

Monitors execution quality metrics:
- fill_rate = filled_signals / total_signals
- avg_realized_slippage_bps = mean(realized - estimated)
- latency_p90_ms
- partial_fill_ratio
- sandwich_evidence_score (optional: sharp adverse move after fill)

Compares paper vs live for degradation detection.

Usage:
    from monitoring.execution_quality_monitor import ExecutionQualityMonitor

    monitor = ExecutionQualityMonitor()
    monitor.add_fills("paper", paper_fills)
    monitor.add_fills("live", live_fills)
    report = monitor.generate_report()
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)


@dataclass
class FillRecord:
    """Single fill record for quality analysis."""
    signal_id: str
    side: str  # BUY | SELL
    estimated_price: float
    realized_price: Optional[float] = None
    estimated_slippage_bps: Optional[float] = None
    realized_slippage_bps: Optional[float] = None
    latency_ms: Optional[int] = None
    fill_status: str = "filled"  # filled | partial | none
    size_remaining: Optional[float] = None
    size_initial: Optional[float] = None
    timestamp: Optional[str] = None
    token_mint: Optional[str] = None
    wallet: Optional[str] = None


@dataclass
class QualityMetrics:
    """Aggregated quality metrics for a set of fills."""
    total_signals: int = 0
    filled_signals: int = 0
    partial_fills: int = 0
    failed_fills: int = 0
    
    # Slippage metrics
    total_estimated_slippage_bps: float = 0.0
    total_realized_slippage_bps: float = 0.0
    slippage_samples: int = 0
    
    # Latency metrics
    latencies_ms: List[int] = field(default_factory=list)
    
    # Size metrics
    total_initial_size: float = 0.0
    total_remaining_size: float = 0.0
    
    @property
    def fill_rate(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.filled_signals / self.total_signals
    
    @property
    def partial_fill_ratio(self) -> float:
        fills = self.filled_signals + self.partial_fills
        if fills == 0:
            return 0.0
        return self.partial_fills / fills
    
    @property
    def avg_estimated_slippage_bps(self) -> float:
        if self.slippage_samples == 0:
            return 0.0
        return self.total_estimated_slippage_bps / self.slippage_samples
    
    @property
    def avg_realized_slippage_bps(self) -> float:
        if self.slippage_samples == 0:
            return 0.0
        return self.total_realized_slippage_bps / self.slippage_samples
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)
    
    @property
    def latency_p90_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.9)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]
    
    @property
    def fill_quality_pct(self) -> float:
        """Percentage of fully filled orders vs partial/failed."""
        fills = self.filled_signals + self.partial_fills + self.failed_fills
        if fills == 0:
            return 0.0
        return self.filled_signals / fills


@dataclass
class QualityComparison:
    """Comparison between two sets of metrics (e.g., paper vs live)."""
    paper_metrics: QualityMetrics
    live_metrics: QualityMetrics
    
    delta_fill_rate: float = 0.0
    delta_avg_slippage_bps: float = 0.0
    delta_latency_p90_ms: float = 0.0
    delta_fill_quality: float = 0.0
    
    @classmethod
    def compare(cls, paper: QualityMetrics, live: QualityMetrics) -> "QualityComparison":
        """Compare paper vs live metrics."""
        comparison = cls(paper_metrics=paper, live_metrics=live)
        comparison.delta_fill_rate = paper.fill_rate - live.fill_rate
        comparison.delta_avg_slippage_bps = (
            paper.avg_realized_slippage_bps - live.avg_realized_slippage_bps
        )
        comparison.delta_latency_p90_ms = paper.latency_p90_ms - live.latency_p90_ms
        comparison.delta_fill_quality = paper.fill_quality_pct - live.fill_quality_pct
        return comparison
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill_rate": {
                "paper": round(self.paper_metrics.fill_rate, 4),
                "live": round(self.live_metrics.fill_rate, 4),
                "delta": round(self.delta_fill_rate, 4),
            },
            "avg_realized_slippage_bps": {
                "paper": round(self.paper_metrics.avg_realized_slippage_bps, 2),
                "live": round(self.live_metrics.avg_realized_slippage_bps, 2),
                "delta": round(self.delta_avg_slippage_bps, 2),
            },
            "latency_p90_ms": {
                "paper": round(self.paper_metrics.latency_p90_ms, 0),
                "live": round(self.live_metrics.latency_p90_ms, 0),
                "delta": round(self.delta_latency_p90_ms, 0),
            },
            "fill_quality_pct": {
                "paper": round(self.paper_metrics.fill_quality_pct, 4),
                "live": round(self.live_metrics.fill_quality_pct, 4),
                "delta": round(self.delta_fill_quality, 4),
            },
        }


class ExecutionQualityMonitor:
    """Monitor for execution quality metrics.
    
    Usage:
        monitor = ExecutionQualityMonitor()
        monitor.add_fills("paper", paper_fills_list)
        monitor.add_fills("live", live_fills_list)
        report = monitor.generate_report()
    """
    
    def __init__(self, slippage_threshold_bps: float = 100.0):
        """Initialize monitor.
        
        Args:
            slippage_threshold_bps: Alert threshold for realized slippage.
        """
        self._fills: Dict[str, List[FillRecord]] = {
            "paper": [],
            "live": [],
        }
        self._metrics: Dict[str, QualityMetrics] = {
            "paper": QualityMetrics(),
            "live": QualityMetrics(),
        }
        self.slippage_threshold_bps = slippage_threshold_bps
    
    def add_fills(self, source: str, fills: List[Dict[str, Any]]) -> None:
        """Add fill records from a source.
        
        Args:
            source: Source name (e.g., "paper", "live").
            fills: List of fill dicts.
        """
        records = []
        for fill in fills:
            record = FillRecord(
                signal_id=fill.get("signal_id", fill.get("tx_hash", "")),
                side=fill.get("side", ""),
                estimated_price=fill.get("estimated_price", fill.get("price", 0.0)),
                realized_price=fill.get("realized_price"),
                estimated_slippage_bps=fill.get("estimated_slippage_bps"),
                realized_slippage_bps=fill.get("realized_slippage_bps"),
                latency_ms=fill.get("latency_ms"),
                fill_status=fill.get("fill_status", fill.get("status", "filled")),
                size_remaining=fill.get("size_remaining"),
                size_initial=fill.get("size_initial"),
                timestamp=fill.get("timestamp"),
                token_mint=fill.get("mint", fill.get("token_mint")),
                wallet=fill.get("wallet"),
            )
            records.append(record)
        
        self._fills[source].extend(records)
        self._recompute_metrics(source)
    
    def add_fill_record(self, source: str, record: FillRecord) -> None:
        """Add a single FillRecord.
        
        Args:
            source: Source name.
            record: FillRecord instance.
        """
        self._fills[source].append(record)
        self._recompute_metrics(source)
    
    def _recompute_metrics(self, source: str) -> None:
        """Recompute metrics for a source."""
        fills = self._fills[source]
        metrics = QualityMetrics()
        
        for fill in fills:
            metrics.total_signals += 1
            
            if fill.fill_status == "filled":
                metrics.filled_signals += 1
            elif fill.fill_status == "partial":
                metrics.partial_fills += 1
            else:
                metrics.failed_fills += 1
            
            # Slippage
            if fill.realized_slippage_bps is not None:
                metrics.total_realized_slippage_bps += fill.realized_slippage_bps
                metrics.slippage_samples += 1
            
            if fill.estimated_slippage_bps is not None:
                metrics.total_estimated_slippage_bps += fill.estimated_slippage_bps
            
            # Latency
            if fill.latency_ms is not None:
                metrics.latencies_ms.append(fill.latency_ms)
            
            # Size
            if fill.size_initial is not None:
                metrics.total_initial_size += fill.size_initial
            if fill.size_remaining is not None:
                metrics.total_remaining_size += fill.size_remaining
        
        self._metrics[source] = metrics
    
    def get_metrics(self, source: str) -> QualityMetrics:
        """Get metrics for a source."""
        return self._metrics.get(source, QualityMetrics())
    
    def compare_paper_live(self) -> QualityComparison:
        """Compare paper vs live metrics."""
        return QualityComparison.compare(
            self._metrics["paper"],
            self._metrics["live"],
        )
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate quality report.
        
        Returns:
            Dict with metrics and alerts.
        """
        paper = self._metrics["paper"]
        live = self._metrics["live"]
        comparison = self.compare_paper_live()
        
        report = {
            "paper": {
                "fill_rate": round(paper.fill_rate, 4),
                "partial_fill_ratio": round(paper.partial_fill_ratio, 4),
                "avg_realized_slippage_bps": round(paper.avg_realized_slippage_bps, 2),
                "avg_estimated_slippage_bps": round(paper.avg_estimated_slippage_bps, 2),
                "latency_p90_ms": round(paper.latency_p90_ms, 0),
                "fill_quality_pct": round(paper.fill_quality_pct, 4),
                "total_signals": paper.total_signals,
            },
            "live": {
                "fill_rate": round(live.fill_rate, 4),
                "partial_fill_ratio": round(live.partial_fill_ratio, 4),
                "avg_realized_slippage_bps": round(live.avg_realized_slippage_bps, 2),
                "avg_estimated_slippage_bps": round(live.avg_estimated_slippage_bps, 2),
                "latency_p90_ms": round(live.latency_p90_ms, 0),
                "fill_quality_pct": round(live.fill_quality_pct, 4),
                "total_signals": live.total_signals,
            },
            "comparison": comparison.to_dict(),
            "alerts": [],
        }
        
        # Generate alerts
        alerts = []
        
        # Slippage alert
        if live.avg_realized_slippage_bps > self.slippage_threshold_bps:
            alert = {
                "level": "WARNING",
                "type": "high_slippage",
                "message": f"High realized slippage: {live.avg_realized_slippage_bps:.1f} bps (threshold: {self.slippage_threshold_bps})",
            }
            alerts.append(alert)
            logger.warning(f"[execution_quality] {alert['message']}")
        
        # Fill rate degradation alert
        if comparison.delta_fill_rate < -0.1:
            alert = {
                "level": "WARNING",
                "type": "fill_rate_drop",
                "message": f"Fill rate dropped by {abs(comparison.delta_fill_rate * 100):.1f}% in live vs paper",
            }
            alerts.append(alert)
            logger.warning(f"[execution_quality] {alert['message']}")
        
        # Latency degradation
        if comparison.delta_latency_p90_ms < -100:
            alert = {
                "level": "WARNING",
                "type": "latency_increase",
                "message": f"Latency P90 increased by {abs(comparison.delta_latency_p90_ms):.0f}ms in live",
            }
            alerts.append(alert)
            logger.warning(f"[execution_quality] {alert['message']}")
        
        report["alerts"] = alerts
        
        return report
    
    def log_report(self) -> None:
        """Log quality report to stderr."""
        report = self.generate_report()
        
        logger.info("[execution_quality] === Execution Quality Report ===")
        logger.info(f"[execution_quality] Paper fill_rate: {report['paper']['fill_rate']:.2%}")
        logger.info(f"[execution_quality] Live fill_rate: {report['live']['fill_rate']:.2%}")
        logger.info(f"[execution_quality] Delta fill_rate: {report['comparison']['fill_rate']['delta']:.2%}")
        logger.info(f"[execution_quality] Live slippage: {report['live']['avg_realized_slippage_bps']:.1f} bps")
        logger.info(f"[execution_quality] Live latency P90: {report['live']['latency_p90_ms']:.0f}ms")
        
        for alert in report["alerts"]:
            logger.log(
                logging.WARNING if alert["level"] == "WARNING" else logging.ERROR,
                f"[execution_quality] ALERT: {alert['message']}"
            )
    
    def to_json(self) -> str:
        """Export report as JSON."""
        return json.dumps(self.generate_report(), indent=2)


def load_fills_from_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load fills from JSONL file.
    
    Args:
        path: Path to JSONL file.
    
    Returns:
        List of fill dicts.
    """
    fills = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                fills.append(json.loads(line))
    return fills


# Self-test
if __name__ == "__main__":
    import tempfile
    
    print("=== ExecutionQualityMonitor Self-Test ===", file=sys.stderr)
    
    # Create sample fills
    paper_fills = [
        {
            "signal_id": "sig_1",
            "side": "BUY",
            "estimated_price": 1.0,
            "realized_price": 1.0008,
            "estimated_slippage_bps": 80,
            "realized_slippage_bps": 75,
            "latency_ms": 200,
            "fill_status": "filled",
            "size_initial": 100.0,
            "size_remaining": 0.0,
        },
        {
            "signal_id": "sig_2",
            "side": "SELL",
            "estimated_price": 1.05,
            "realized_price": 1.0492,
            "estimated_slippage_bps": 80,
            "realized_slippage_bps": 85,
            "latency_ms": 180,
            "fill_status": "filled",
            "size_initial": 100.0,
            "size_remaining": 0.0,
        },
    ]
    
    live_fills = [
        {
            "signal_id": "sig_1",
            "side": "BUY",
            "estimated_price": 1.0,
            "realized_price": 1.002,
            "estimated_slippage_bps": 80,
            "realized_slippage_bps": 190,
            "latency_ms": 450,
            "fill_status": "filled",
            "size_initial": 100.0,
            "size_remaining": 0.0,
        },
        {
            "signal_id": "sig_2",
            "side": "SELL",
            "estimated_price": 1.05,
            "realized_price": 1.05,
            "estimated_slippage_bps": 80,
            "realized_slippage_bps": 80,
            "latency_ms": 380,
            "fill_status": "partial",
            "size_initial": 100.0,
            "size_remaining": 50.0,
        },
    ]
    
    # Test monitor
    monitor = ExecutionQualityMonitor(slippage_threshold_bps=100.0)
    monitor.add_fills("paper", paper_fills)
    monitor.add_fills("live", live_fills)
    
    print(f"Paper fill_rate: {monitor.get_metrics('paper').fill_rate:.2%}", file=sys.stderr)
    print(f"Live fill_rate: {monitor.get_metrics('live').fill_rate:.2%}", file=sys.stderr)
    print(f"Paper avg slippage: {monitor.get_metrics('paper').avg_realized_slippage_bps:.1f} bps", file=sys.stderr)
    print(f"Live avg slippage: {monitor.get_metrics('live').avg_realized_slippage_bps:.1f} bps", file=sys.stderr)
    
    # Generate report
    report = monitor.generate_report()
    print(f"\nComparison: {report['comparison']}", file=sys.stderr)
    
    print(f"\nAlerts: {len(report['alerts'])}", file=sys.stderr)
    for alert in report["alerts"]:
        print(f"  - {alert['level']}: {alert['message']}", file=sys.stderr)
    
    # Verify alerts
    assert len(report["alerts"]) == 2, "Expected 2 alerts"
    
    print("\n=== All tests passed! ===", file=sys.stderr)
