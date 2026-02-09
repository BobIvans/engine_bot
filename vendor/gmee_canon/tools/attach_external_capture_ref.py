#!/usr/bin/env python3
from __future__ import annotations

"""Attach an external capture reference to a trace/trade via forensics_events.

P0-safe: uses existing forensics_events(details_json).

Example:
  CLICKHOUSE_HTTP_URL=http://localhost:8123 \
  python tools/attach_external_capture_ref.py \
    --chain sol --env dev \
    --trade-id ... --trace-id ... \
    --provider-id nansen --snapshot-id 2025... --license-tag nansen_trial
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.models import WriterContext
from gmee.forensics import emit_external_capture_ref


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--chain', required=True)
    ap.add_argument('--env', required=True)
    ap.add_argument('--trace-id', default=None)
    ap.add_argument('--trade-id', default=None)
    ap.add_argument('--attempt-id', default=None)
    ap.add_argument('--provider-id', required=True)
    ap.add_argument('--snapshot-id', required=True)
    ap.add_argument('--license-tag', required=True)
    ap.add_argument('--raw-sha256', default=None)
    ap.add_argument('--uv-sha256', default=None)
    args = ap.parse_args()

    runner = ClickHouseQueryRunner.from_env()
    ctx = WriterContext(chain=args.chain, env=args.env, experiment_id='external_capture', config_hash='external_capture')

    emit_external_capture_ref(
        runner,
        ctx,
        trace_id=args.trace_id,
        trade_id=args.trade_id,
        attempt_id=args.attempt_id,
        provider_id=args.provider_id,
        snapshot_id=args.snapshot_id,
        license_tag=args.license_tag,
        raw_sha256=args.raw_sha256,
        uv_sha256=args.uv_sha256,
    )

    print('ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
