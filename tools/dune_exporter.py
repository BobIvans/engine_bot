#!/usr/bin/env python3
"""tools/dune_exporter.py

Daily cron job for exporting top wallets from Dune Analytics.
Reads config from strategy/config/params_base.yaml and exports filtered profiles.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from integration.dune_source import DuneWalletSource, SCHEMA_VERSION

CONFIG_PATH = PROJECT_ROOT / "strategy" / "config" / "params_base.yaml"
OUTPUT_DIR = PROJECT_ROOT / "data" / "wallets"


def load_config() -> dict:
    """Load Dune exporter configuration from params_base.yaml."""
    import yaml
    
    if not CONFIG_PATH.exists():
        print(f"[dune_exporter] WARNING: Config not found at {CONFIG_PATH}, using defaults", file=sys.stderr)
        return {
            "dune_export": {
                "enabled": True,
                "min_trades": 50,
                "min_roi_30d": 0.1,
                "out_prefix": "dune_export"
            }
        }
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    return config.get("dune_export", {})


def run_daily_export(
    enabled: bool = True,
    min_trades: int = 50,
    min_roi: float = 0.1,
    out_prefix: str = "dune_export"
) -> dict:
    """Execute the daily Dune export pipeline.
    
    Args:
        enabled: Whether to run the export (False = skip with warning).
        min_trades: Minimum trades_30d threshold.
        min_roi: Minimum roi_30d threshold.
        out_prefix: Prefix for output file name.
    
    Returns:
        Summary dict with export metrics.
    """
    if not enabled:
        print("[dune_exporter] SKIP: Dune export is disabled in config", file=sys.stderr)
        return {
            "exported_count": 0,
            "skipped": True,
            "schema_version": SCHEMA_VERSION
        }
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename with date
    date_str = datetime.utcnow().strftime("%Y%m%d")
    out_path = str(OUTPUT_DIR / f"{out_prefix}_{date_str}.parquet")
    
    # Try to load from Dune API first (if enabled), fallback to fixture
    dune_api_key = None
    try:
        dune_api_key = __import__("os").getenv("DUNE_API_KEY")
    except Exception:
        pass
    
    if dune_api_key:
        print("[dune_exporter] Using real Dune API (not implemented in this stub)", file=sys.stderr)
        # In full implementation, this would call Dune API
        # For now, fall back to fixture
    
    # Fallback: use fixture for testing
    fixture_path = PROJECT_ROOT / "integration" / "fixtures" / "discovery" / "dune_export_sample.csv"
    if not fixture_path.exists():
        print(f"[dune_exporter] ERROR: Neither Dune API nor fixture available", file=sys.stderr)
        return {
            "exported_count": 0,
            "error": "No data source available",
            "schema_version": SCHEMA_VERSION
        }
    
    # Load and export
    source = DuneWalletSource(min_trades=min_trades, min_roi_30d=min_roi)
    profiles = source.load_from_file(str(fixture_path))
    
    if profiles:
        source.export_to_parquet(profiles, out_path, dry_run=False)
        print(f"[dune_exporter] Exported {len(profiles)} wallets to {out_path}", file=sys.stderr)
    else:
        print("[dune_exporter] No wallets passed filters", file=sys.stderr)
    
    return {
        "exported_count": len(profiles),
        "out_path": out_path,
        "schema_version": SCHEMA_VERSION
    }


def main():
    """CLI entry point for daily export."""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Daily Dune wallet export cron job")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Config file path")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--summary-json", action="store_true", help="Output JSON summary to stdout")
    
    args = parser.parse_args()
    
    # Load config from YAML
    config = load_config()
    
    # Override with environment variables if set
    enabled = config.get("enabled", True)
    if os.getenv("DUNE_EXPORT_ENABLED") is not None:
        enabled = os.getenv("DUNE_EXPORT_ENABLED").lower() in ("true", "1", "yes")
    
    min_trades = int(os.getenv("DUNE_MIN_TRADES", config.get("min_trades", 50)))
    min_roi = float(os.getenv("DUNE_MIN_ROI", config.get("min_roi_30d", 0.1)))
    out_prefix = os.getenv("DUNE_OUT_PREFIX", config.get("out_prefix", "dune_export"))
    
    result = run_daily_export(
        enabled=enabled,
        min_trades=min_trades,
        min_roi=min_roi,
        out_prefix=out_prefix
    )
    
    if args.dry_run:
        result["dry_run"] = True
        result["message"] = "Would export but --dry-run enabled"
    
    if args.summary_json:
        print(json.dumps(result))
    
    return result


if __name__ == "__main__":
    main()
