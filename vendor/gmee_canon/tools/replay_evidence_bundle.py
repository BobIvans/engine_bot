#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.replay import replay_any_evidence_bundle


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay GMEE P0 evidence bundle into ClickHouse (trade or trace).")
    ap.add_argument("--bundle", required=True, help="Bundle directory (trade bundle has manifest.json; trace bundle has trace_manifest.json)")
    ap.add_argument("--no-skip-existing", action="store_true", help="Do not skip when rows exist (append).")
    ap.add_argument("--force", action="store_true", help="DELETE existing rows for this trade/trace before inserting (mutations_sync=2).")
    ap.add_argument("--no-verify", action="store_true", help="Do not verify sha256")
    args = ap.parse_args()

    runner = ClickHouseQueryRunner.from_env()
    replay_any_evidence_bundle(
        runner,
        Path(args.bundle),
        skip_existing=not args.no_skip_existing,
        force=args.force,
        verify_hashes=not args.no_verify,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
