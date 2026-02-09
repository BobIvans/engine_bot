#!/usr/bin/env bash
set -euo pipefail

python3 -m integration.validate_jsonl_schema --schema integration/schemas/token_snapshot_schema.json --jsonl integration/fixtures/token_snapshot.sample.jsonl
python3 -m integration.validate_jsonl_schema --schema integration/schemas/wallet_profile_schema.json --jsonl integration/fixtures/wallet_profile.sample.jsonl
python3 -m integration.validate_jsonl_schema --schema integration/schemas/signal_schema.json --jsonl integration/fixtures/signal.sample.jsonl
python3 -m integration.validate_jsonl_schema --schema integration/schemas/sim_fill_schema.json --jsonl integration/fixtures/sim_fill.sample.jsonl
python3 -m integration.validate_jsonl_schema --schema integration/schemas/position_pnl_schema.json --jsonl integration/fixtures/position_pnl.sample.jsonl

echo "[schema_smoke] OK"
