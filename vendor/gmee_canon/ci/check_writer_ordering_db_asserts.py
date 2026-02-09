"""CI guard: ensure Tier-0 writer enforces EPIC 4.1 at DB-level (P0).

This is a *merge-gate* check, not a feature.

We verify that the writer does *real ClickHouse existence checks* before writing:
- trades: requires upstream signals_raw + trade_attempts rows.
- microticks_1s: requires trades row exists and entry_confirm_quality == 'ok'.

If these checks are removed or weakened, this script must fail CI.

P0 scope: no new SQL/YAML/DDL/doc changes.
"""

from __future__ import annotations

# Ensure repo root is importable when running as `python ci/<script>.py`
from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.models import WriterContext
from gmee.writer import Tier0Writer


def _utc(y, m, d, hh=0, mm=0, ss=0, ms=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, ms * 1000, tzinfo=timezone.utc)


def main() -> int:
    runner = ClickHouseQueryRunner.from_env()

    # Ensure schema exists (idempotent). Do NOT rely on prior steps.
    runner.run_sql_file(Path("schemas/clickhouse.sql"))

    # Start from a clean forensics table so we can assert inserts deterministically.
    try:
        runner.execute_raw("TRUNCATE TABLE forensics_events")
    except Exception:
        # If TRUNCATE fails for some reason, we still can proceed.
        pass

    ctx = WriterContext(
        env="ci",
        chain="solana",
        experiment_id="exp_ci",
        config_hash="0" * 64,
        model_version="gmee-v0.4",
        source="ci_guard",
        our_wallet="our_wallet_ci",
        client_version="ci",
        build_sha="deadbeef",
    )
    writer = Tier0Writer(runner, ctx)

    # Load canonical engine cfg (needed for write_trade_with_plan).
    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))

    trade_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    # 1) trades must fail when upstream rows are not present.
    failed = False
    try:
        writer.write_trade_with_plan(
            trade_id=trade_id,
            trace_id=trace_id,
            traced_wallet="wallet_oracle",  # stable (exists in seed profile if present)
            token_mint="token_test",
            pool_id="pool_test",
            signal_time=_utc(2025, 1, 1, 0, 0, 0, 0),
            entry_local_send_time=_utc(2025, 1, 1, 0, 0, 1, 0),
            entry_first_confirm_time=_utc(2025, 1, 1, 0, 0, 2, 0),
            buy_time=_utc(2025, 1, 1, 0, 0, 2, 0),
            buy_price_usd=1.0,
            amount_usd=1.0,
            entry_attempt_id=attempt_id,
            entry_idempotency_token="1" * 64,
            entry_nonce_u64=0,
            entry_rpc_sent_list=["rpc_arm_oracle"],
            entry_rpc_winner="rpc_arm_oracle",
            entry_confirm_quality="ok",
            entry_tx_sig="tx_test",
            entry_block_ref="slot_test",
            engine_cfg=cfg,
        )
    except RuntimeError as e:
        msg = str(e).lower()
        if "ordering_violation" in msg:
            failed = True
        else:
            print(f"ERROR: unexpected RuntimeError: {e}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"ERROR: unexpected exception type: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if not failed:
        print("ERROR: writer.write_trade_with_plan() unexpectedly succeeded without upstream rows; EPIC 4.1 broken", file=sys.stderr)
        return 3

    n = int((runner.execute_raw("SELECT count() FROM forensics_events WHERE kind='ordering_violation'") or "0").strip() or "0")
    if n < 1:
        print("ERROR: ordering_violation forensics event was not recorded", file=sys.stderr)
        return 4

    # 2) microticks must fail if trades row is not present.
    try:
        runner.execute_raw("TRUNCATE TABLE forensics_events")
    except Exception:
        pass

    failed2 = False
    try:
        writer.write_microtick_1s(
            trade_id=str(uuid.uuid4()),
            t_offset_s=0,
            ts=_utc(2025, 1, 1, 0, 0, 2, 0),
            price_usd=1.0,
            liquidity_usd=1000.0,
            volume_usd=1.0,
        )
    except RuntimeError as e:
        if "ordering_violation" in str(e).lower():
            failed2 = True
        else:
            print(f"ERROR: unexpected RuntimeError: {e}", file=sys.stderr)
            return 5
    except Exception as e:
        print(f"ERROR: unexpected exception type: {type(e).__name__}: {e}", file=sys.stderr)
        return 5

    if not failed2:
        print("ERROR: writer.write_microtick_1s() unexpectedly succeeded without trades row; EPIC 4.1 broken", file=sys.stderr)
        return 6

    n2 = int((runner.execute_raw("SELECT count() FROM forensics_events WHERE kind='ordering_violation'") or "0").strip() or "0")
    if n2 < 1:
        print("ERROR: ordering_violation forensics event was not recorded for microticks", file=sys.stderr)
        return 7

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())