"""monitoring/exporters.py

PR-D.4 Metrics Export.

Persist session metrics (PnL, Winrate, Fill Rate) to CSV/Parquet.

Design goals:
- CSV: Simple append (creates header if missing)
- Parquet: Optional (falls back to CSV if unavailable)
- Clean stdout (logs to stderr)
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def flatten_metrics(
    metrics: Dict[str, Any],
    prefix: str = "",
    delimiter: str = "_",
) -> Dict[str, Any]:
    """Flatten nested metrics dict to single-level dict.

    Args:
        metrics: Nested metrics dictionary.
        prefix: Prefix for nested keys.
        delimiter: Delimiter for nested keys.

    Returns:
        Flattened dictionary.
    """
    flat: Dict[str, Any] = {}

    for key, value in metrics.items():
        new_key = f"{prefix}{delimiter}{key}" if prefix else key

        if isinstance(value, dict):
            flat.update(flatten_metrics(value, new_key, delimiter))
        elif isinstance(value, list):
            # Convert lists to comma-separated strings
            flat[new_key] = ",".join(str(v) for v in value)
        else:
            flat[new_key] = value

    return flat


def export_run_metrics(
    metrics: Dict[str, Any],
    path: str,
    format: str = "csv",
    timestamp: Optional[str] = None,
) -> bool:
    """Export run metrics to file.

    Args:
        metrics: Metrics dictionary to export.
        path: Output file path.
        format: Export format ("csv" or "parquet").
        timestamp: Optional timestamp (defaults to now).

    Returns:
        True if exported successfully.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()

    # Flatten metrics
    flat_metrics = flatten_metrics(metrics)
    flat_metrics["timestamp"] = timestamp

    # Ensure directory exists
    output_path = Path(path)
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "csv":
        return _export_csv(flat_metrics, path)
    elif format == "parquet":
        return _export_parquet(flat_metrics, path)
    else:
        print(f"[Export] Unknown format: {format}, falling back to CSV", file=sys.stderr)
        return _export_csv(flat_metrics, path)


def _export_csv(metrics: Dict[str, Any], path: str) -> bool:
    """Export metrics to CSV (append mode).

    Args:
        metrics: Flattened metrics dictionary.
        path: Output file path.

    Returns:
        True if exported successfully.
    """
    file_exists = Path(path).exists()
    fieldnames = list(metrics.keys())

    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(metrics)

        print(f"[Export] CSV appended: {path}", file=sys.stderr)
        return True

    except Exception as e:
        print(f"[Export] CSV write error: {e}", file=sys.stderr)
        return False


def _export_parquet(metrics: Dict[str, Any], path: str) -> bool:
    """Export metrics to Parquet (fallback to CSV on error).

    Args:
        metrics: Flattened metrics dictionary.
        path: Output file path.

    Returns:
        True if exported successfully.
    """
    try:
        import pandas as pd

        df = pd.DataFrame([metrics])
        df.to_parquet(path, index=False)
        print(f"[Export] Parquet written: {path}", file=sys.stderr)
        return True

    except ImportError:
        print("[Export] pandas not available, falling back to CSV", file=sys.stderr)
        return _export_csv(metrics, path.replace(".parquet", ".csv"))

    except Exception as e:
        print(f"[Export] Parquet write error: {e}", file=sys.stderr)
        # Try CSV fallback
        csv_path = path.replace(".parquet", ".csv")
        return _export_csv(metrics, csv_path)


def export_session_summary(
    session_stats: Dict[str, Any],
    path: str,
) -> bool:
    """Export session summary metrics.

    Args:
        session_stats: Session statistics dictionary.
        path: Output file path.

    Returns:
        True if exported successfully.
    """
    return export_run_metrics(session_stats, path, format="csv")


def export_trade_log(
    trades: List[Dict[str, Any]],
    path: str,
) -> bool:
    """Export trade log to CSV.

    Args:
        trades: List of trade dictionaries.
        path: Output file path.

    Returns:
        True if exported successfully.
    """
    if not trades:
        print("[Export] No trades to export", file=sys.stderr)
        return True

    # Flatten each trade
    flat_trades = [flatten_metrics(t) for t in trades]

    # Get all fieldnames
    fieldnames = set()
    for trade in flat_trades:
        fieldnames.update(trade.keys())
    fieldnames = sorted(fieldnames)

    # Add timestamp to each trade
    timestamp = datetime.utcnow().isoformat()
    for trade in flat_trades:
        trade["export_timestamp"] = timestamp

    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not Path(path).exists():
                writer.writeheader()
            writer.writerows(flat_trades)

        print(f"[Export] Trade log appended: {path} ({len(trades)} trades)", file=sys.stderr)
        return True

    except Exception as e:
        print(f"[Export] Trade log error: {e}", file=sys.stderr)
        return False


class MetricsExporter:
    """Simple metrics exporter for repeated exports."""

    def __init__(self, base_path: str, format: str = "csv"):
        """Initialize exporter.

        Args:
            base_path: Base directory for metrics files.
            format: Export format (csv/parquet).
        """
        self.base_path = Path(base_path)
        self.format = format
        self.base_path.mkdir(parents=True, exist_ok=True)

    def export_session(self, session_stats: Dict[str, Any]) -> bool:
        """Export session stats."""
        path = self.base_path / "session_summary.csv"
        return export_session_summary(session_stats, str(path))

    def export_trades(self, trades: List[Dict[str, Any]]) -> bool:
        """Export trade log."""
        path = self.base_path / "trades.csv"
        return export_trade_log(trades, str(path))

    def export_custom(
        self,
        name: str,
        metrics: Dict[str, Any],
    ) -> bool:
        """Export custom metrics."""
        path = self.base_path / f"{name}.csv"
        return export_run_metrics(metrics, str(path), format=self.format)
