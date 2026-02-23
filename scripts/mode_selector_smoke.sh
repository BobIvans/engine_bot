#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[mode_selector_smoke] Starting mode selector smoke test..." >&2
echo "[mode_selector_smoke] ROOT_DIR=${ROOT_DIR}" >&2

cd "${ROOT_DIR}"

unset PYTHONPATH
export PYTHONPATH="${ROOT_DIR}"

python3 - <<'PY'
import os, sys, inspect
from types import SimpleNamespace

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path = [p for p in sys.path if "strategy pack" not in (p or "")]

from strategy.mode_selector import select_mode
from integration.token_snapshot_store import TokenSnapshot

sig = inspect.signature(select_mode)
print(f"[mode_selector_smoke] select_mode signature: {sig}", file=sys.stderr)

passed = 0
failed = 0

# One config object, mirrored into multiple likely keys (SoT may differ)
mode_cfg = {
    "default_mode": "L",
    "hold_thresholds_sec": {"U": 40, "S": 120, "M": 240},
    "enable_aggressive": True,
    "aggressive_min_impulse_pct": 3.0,
    "aggressive_min_impulse_count": 1,
}

cfg = {
    "mode_selector": mode_cfg,
    "mode": mode_cfg,
    "modes": mode_cfg,
    "strategy": {"mode_selector": mode_cfg},
}

def wp(median_hold_sec, impulse_count=0, impulse_pct=0.0):
    return SimpleNamespace(
        wallet="X",
        tier="A",
        median_hold_sec=median_hold_sec,
        impulse_count=impulse_count,
        impulse_max_pct=impulse_pct,
        winrate_7d=0.6,
        pnl_7d_usd=100.0,
    )

def call_select_mode(wallet_profile, token_snapshot):
    return select_mode(wallet_profile, token_snapshot, cfg)

def assert_tuple(name, out):
    global passed, failed
    ok = isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], str) and isinstance(out[1], str)
    if ok:
        print(f"  [mode_selector] {name}: PASS (mode={out[0]}, reason={out[1]})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [mode_selector] {name}: FAIL (bad return shape: {out!r})", file=sys.stderr)
        failed += 1

print("[mode_selector_smoke] Running pure logic tests...", file=sys.stderr)

snap = TokenSnapshot(mint="So11111111111111111111111111111111111111112", liquidity_usd=50000.0, extra={})

# Primary: just ensure stable, correct return type across scenarios
assert_tuple("fast_scalper", call_select_mode(wp(20), snap))
assert_tuple("medium_scalper", call_select_mode(wp(75), snap))
assert_tuple("swing_trader", call_select_mode(wp(180), snap))
assert_tuple("long_holder", call_select_mode(wp(300), snap))
assert_tuple("no_profile", call_select_mode(None, snap))
assert_tuple("no_median_hold", call_select_mode(wp(None), snap))
assert_tuple("boundary_40s", call_select_mode(wp(40), snap))
assert_tuple("aggressive_trigger", call_select_mode(wp(20, impulse_count=3, impulse_pct=5.0), snap))
assert_tuple("aggressive_not_trigger", call_select_mode(wp(20, impulse_count=1, impulse_pct=2.0), snap))
assert_tuple("no_snapshot", call_select_mode(wp(20, impulse_count=3, impulse_pct=5.0), None))

print("[mode_selector_smoke] Running signal engine integration test...", file=sys.stderr)

from strategy.signal_engine import decide_entry
from integration.trade_types import Trade

trade = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="test_wallet",
    mint="So11111111111111111111111111111111111111112",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    tx_hash="0x123",
)

decision = decide_entry(trade=trade, snapshot=snap, wallet_profile=None, cfg={"token_profile": {"honeypot": {"enabled": False}}})
if hasattr(decision, "should_enter"):
    print("  [mode_selector] signal_engine_import: PASS", file=sys.stderr)
    passed += 1
else:
    print("  [mode_selector] signal_engine_import: FAIL (no should_enter)", file=sys.stderr)
    failed += 1

print(f"\n[mode_selector_smoke] Results: {passed} passed, {failed} failed", file=sys.stderr)
if failed:
    sys.exit(1)

print("[mode_selector_smoke] OK ✅", file=sys.stderr)
PY
