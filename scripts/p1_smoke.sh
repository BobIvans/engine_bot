#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

ALLOWLIST_PATH="${ALLOWLIST_PATH:-$ROOT_DIR/strategy/wallet_allowlist.yaml}"
FEATURES_FILE="${FEATURES_FILE:-$ROOT_DIR/strategy/wallet_features_example.json}"

# Optional explicit wallet override
TEST_WALLET="${TEST_WALLET:-}"

echo "[p1_smoke] overlay drift lint..."
bash "$ROOT_DIR/scripts/overlay_lint.sh"

echo "[p1_smoke] running Iteration-1 chain (P0)..."
bash "$ROOT_DIR/scripts/iteration1.sh"

if [[ -z "$TEST_WALLET" ]]; then
  echo "[p1_smoke] selecting first wallet from allowlist: $ALLOWLIST_PATH"
  TEST_WALLET="$(ALLOWLIST_PATH=\"$ALLOWLIST_PATH\" python3 - <<'PY'
import os
from integration.allowlist_loader import load_allowlist
path = os.environ.get("ALLOWLIST_PATH","strategy/wallet_allowlist.yaml")
wallets, _h = load_allowlist(path)
print(wallets[0] if wallets else "")
PY
)"
fi

if [[ -z "$TEST_WALLET" ]]; then
  echo "[p1_smoke] ERROR: allowlist is empty and TEST_WALLET not provided."
  echo "Set TEST_WALLET=... or add at least one wallet to strategy/wallet_allowlist.yaml"
  exit 2
fi

TOKEN_MINT="${TOKEN_MINT:-So11111111111111111111111111111111111111112}"
POOL_ID="${POOL_ID:-pool_test_001}"

echo "[p1_smoke] writing test signal to signals_raw..."
python3 -m integration.write_signal   --traced-wallet "$TEST_WALLET"   --token-mint "$TOKEN_MINT"   --pool-id "$POOL_ID"   --allowlist-path "$ALLOWLIST_PATH"   --require-allowlist

echo "[p1_smoke] writing test wallet_score to forensics_events..."
python3 -m integration.write_wallet_score   --wallet "$TEST_WALLET"   --score 0.82   --features-file "$FEATURES_FILE"   --allowlist-path "$ALLOWLIST_PATH"

echo "[p1_smoke] verifying ClickHouse rows exist..."
python3 - <<PY
import os, sys
from pathlib import Path

REPO_ROOT = Path("${ROOT_DIR}")
VENDOR = REPO_ROOT / "vendor" / "gmee_canon"
sys.path.insert(0, str(VENDOR))
from gmee.clickhouse import ClickHouseQueryRunner  # type: ignore

ch_url = os.getenv("CLICKHOUSE_URL","http://localhost:8123")
ch_user = os.getenv("CLICKHOUSE_USER","default")
ch_password = os.getenv("CLICKHOUSE_PASSWORD","")

runner = ClickHouseQueryRunner(base_url=ch_url, user=ch_user, password=ch_password)

wallet = "${TEST_WALLET}"
sig_cnt = runner.select_int("SELECT count() FROM signals_raw WHERE traced_wallet = %(w)s", params={"w": wallet})
score_cnt = runner.select_int(
    "SELECT count() FROM forensics_events WHERE kind='wallet_score' AND JSONExtractString(details_json,'traced_wallet') = %(w)s",
    params={"w": wallet},
)
alv_cnt = runner.select_int("SELECT count() FROM forensics_events WHERE kind='allowlist_version'")
cfg_cnt = runner.select_int("SELECT count() FROM forensics_events WHERE kind='config_version'")

print(f"[p1_smoke] signals_raw rows for wallet: {sig_cnt}")
print(f"[p1_smoke] wallet_score events for wallet: {score_cnt}")
print(f"[p1_smoke] allowlist_version events: {alv_cnt}")
print(f"[p1_smoke] config_version events: {cfg_cnt}")

if sig_cnt < 1:
    raise SystemExit("Expected >=1 signals_raw row for test wallet")
if score_cnt < 1:
    raise SystemExit("Expected >=1 wallet_score event for test wallet")
if alv_cnt < 1:
    raise SystemExit("Expected >=1 allowlist_version event")
if cfg_cnt < 1:
    raise SystemExit("Expected >=1 config_version event")
print("[p1_smoke] OK ✅")
PY
