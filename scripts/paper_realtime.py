#!/usr/bin/env python3
"""scripts/paper_realtime.py

CLI entrypoint for the realtime paper runner.

Usage:
    python scripts/paper_realtime.py --config <config.yaml> --allowlist <wallets.txt> [--interval-sec 5] [--dry-run]

Options:
    --config: Path to strategy config YAML
    --allowlist: Path to wallet allowlist (one wallet per line)
    --interval-sec: Poll interval in seconds [default: 5]
    --dry-run: Run without executing paper trades
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from integration.config_loader import load_params_base
from integration.realtime_runner import RealtimeRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime paper runner for copy-trading strategy")
    parser.add_argument("--config", type=str, required=True, help="Path to strategy config YAML")
    parser.add_argument("--allowlist", type=str, required=True, help="Path to wallet allowlist (one wallet per line)")
    parser.add_argument("--interval-sec", type=int, default=5, help="Poll interval in seconds [default: 5]")
    parser.add_argument("--dry-run", action="store_true", help="Run without executing paper trades")
    return parser.parse_args()


def load_wallets(path: str) -> List[str]:
    """Load wallet addresses from file (one per line)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Allowlist not found: {path}")

    wallets = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            wallets.append(line)
    return wallets


def main() -> None:
    args = parse_args()

    # Load config
    try:
        loaded = load_params_base(args.config)
        config = loaded.config
        print(f"[paper_realtime] Loaded config: {loaded.strategy_name} v{loaded.version}", file=sys.stderr)
    except Exception as e:
        print(f"[paper_realtime] Config error: {e}", file=sys.stderr)
        sys.exit(1)

    # Load wallets
    try:
        wallets = load_wallets(args.allowlist)
        print(f"[paper_realtime] Loaded {len(wallets)} wallets from {args.allowlist}", file=sys.stderr)
    except Exception as e:
        print(f"[paper_realtime] Allowlist error: {e}", file=sys.stderr)
        sys.exit(1)

    # Add tracked_wallets to config
    config["tracked_wallets"] = wallets

    # Dry-run mode
    if args.dry_run:
        print("[paper_realtime] DRY RUN MODE - no paper trades will be executed", file=sys.stderr)
        config["dry_run"] = True

    # Create mock source and snapshot store for now
    # In production, these would be real implementations
    class MockSource:
        def poll_new_records(self, wallet, stop_at_signature=None, limit=50):
            return []

    class MockSnapshotStore:
        def get(self, mint):
            return None

    source = MockSource()
    snapshot_store = MockSnapshotStore()

    # Create and run runner
    runner = RealtimeRunner(
        config=config,
        source=source,
        snapshot_store=snapshot_store,
        interval_sec=args.interval_sec,
    )

    print("[paper_realtime] Starting realtime runner...", file=sys.stderr)

    try:
        runner.run_loop()
    except KeyboardInterrupt:
        print("\n[paper_realtime] Interrupted by user", file=sys.stderr)
    except Exception as e:
        print(f"[paper_realtime] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
