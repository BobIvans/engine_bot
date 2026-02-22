#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[inference_smoke] Starting Inference Wiring smoke test..." >&2
echo "[inference_smoke] ROOT_DIR=${ROOT_DIR}" >&2

cd "${ROOT_DIR}"

unset PYTHONPATH
export PYTHONPATH="${ROOT_DIR}"

python3 - <<'PY'
import os, sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path = [p for p in sys.path if "strategy pack" not in (p or "")]

# Sanity: ensure we import from THIS repo
import strategy.signal_engine as se
print("[inference_smoke] signal_engine module:", se.__file__, file=sys.stderr)

# Minimal wiring check: import key entrypoints
from strategy.signal_engine import decide_entry
from integration.token_snapshot_store import TokenSnapshot
from integration.trade_types import Trade

snap = TokenSnapshot(mint="So11111111111111111111111111111111111111112", liquidity_usd=50000.0, extra={})

trade = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="test_wallet",
    mint=snap.mint,
    side="BUY",
    price=1.0,
    size_usd=50.0,
    tx_hash="0xinf",
)

decision = decide_entry(trade=trade, snapshot=snap, wallet_profile=None, cfg={"token_profile": {"honeypot": {"enabled": False}}})
assert hasattr(decision, "should_enter"), "decision missing should_enter"
print("[inference_smoke] OK ✅", file=sys.stderr)
PY
