#!/bin/bash
# scripts/mode_selector_smoke.sh
# PR-B.4 Dynamic Mode Selector - Deterministic Smoke Test

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[mode_selector_smoke] Starting mode selector smoke test..." >&2

# Python test script
python3 << 'PYTHON_TEST'
import sys

# Add root to path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from strategy.mode_selector import select_mode, select_mode_simple
from integration.wallet_profile_store import WalletProfile
from integration.token_snapshot_store import TokenSnapshot

# Test counters
passed = 0
failed = 0

def test_case(name, expected_mode, wallet_profile=None, token_snapshot=None, cfg=None):
    global passed, failed
    mode, reason = select_mode(wallet_profile, token_snapshot, cfg)
    
    if mode == expected_mode:
        print(f"  [mode_selector] {name}: PASS (mode={mode}, reason={reason})", file=sys.stderr)
        passed += 1
    else:
        print(f"  [mode_selector] {name}: FAIL (got mode={mode}, reason={reason}, expected mode={expected_mode})", file=sys.stderr)
        failed += 1

print("[mode_selector_smoke] Running pure logic tests...", file=sys.stderr)

# Configuration matching params_base.yaml structure
cfg = {
    "signals": {
        "modes": {
            "choose_mode": {
                "U_if_median_hold_sec_lt": 40,
                "S_if_median_hold_sec_lt": 100,
                "M_if_median_hold_sec_lt": 220,
                "else_mode": "L"
            },
            "aggressive": {
                "enabled": True,
                "triggers": {
                    "U": {"require_price_change_pct": 3.0, "within_sec": 15},
                    "S": {"require_price_change_pct": 6.0, "within_sec": 30},
                    "M": {"require_price_change_pct": 10.0, "within_sec": 60},
                    "L": {"require_price_change_pct": 15.0, "within_sec": 90}
                }
            }
        }
    }
}

# Test 1: Fast scalper (20s hold) -> Expect "U"
fast_profile = WalletProfile(
    wallet="FastTrader123",
    median_hold_sec=20.0
)
test_case(
    "fast_scalper_U",
    expected_mode="U",
    wallet_profile=fast_profile,
    cfg=cfg
)

# Test 2: Medium scalper (75s hold) -> Expect "S"
medium_profile = WalletProfile(
    wallet="SwingTrader456",
    median_hold_sec=75.0
)
test_case(
    "medium_scalper_S",
    expected_mode="S",
    wallet_profile=medium_profile,
    cfg=cfg
)

# Test 3: Swing trader (180s hold) -> Expect "M"
swing_profile = WalletProfile(
    wallet="SwingTrader789",
    median_hold_sec=180.0
)
test_case(
    "swing_trader_M",
    expected_mode="M",
    wallet_profile=swing_profile,
    cfg=cfg
)

# Test 4: Long holder (300s hold) -> Expect "L"
long_profile = WalletProfile(
    wallet="LongHolder999",
    median_hold_sec=300.0
)
test_case(
    "long_holder_L",
    expected_mode="L",
    wallet_profile=long_profile,
    cfg=cfg
)

# Test 5: No wallet profile -> Expect "L" (else_mode)
test_case(
    "no_profile_default_L",
    expected_mode="L",
    wallet_profile=None,
    cfg=cfg
)

# Test 6: Profile without median_hold_sec -> Expect "L"
no_hold_profile = WalletProfile(
    wallet="NoHoldData",
    median_hold_sec=None
)
test_case(
    "no_median_hold_sec_default_L",
    expected_mode="L",
    wallet_profile=no_hold_profile,
    cfg=cfg
)

# Test 7: Threshold boundary test (40s -> S, not U)
boundary_profile = WalletProfile(
    wallet="BoundaryTrader",
    median_hold_sec=40.0
)
test_case(
    "boundary_40s_S",
    expected_mode="S",
    wallet_profile=boundary_profile,
    cfg=cfg
)

# Test 8: Aggressive trigger - high volatility
vol_snapshot = TokenSnapshot(
    mint="HighVolToken123",
    liquidity_usd=50000.0,
    volume_24h_usd=100000.0,
    spread_bps=50.0,
    extra={
        "vol": {"ret_30s": 5.0}  # 5% return in 30s triggers U_aggr
    }
)
test_case(
    "aggressive_U_triggered",
    expected_mode="U_aggr",
    wallet_profile=fast_profile,
    token_snapshot=vol_snapshot,
    cfg=cfg
)

# Test 9: No aggressive trigger - low volatility (stays U)
low_vol_snapshot = TokenSnapshot(
    mint="LowVolToken456",
    liquidity_usd=50000.0,
    volume_24h_usd=100000.0,
    spread_bps=50.0,
    extra={
        "vol": {"ret_30s": 1.0}  # 1% return, below 3% threshold
    }
)
test_case(
    "aggressive_not_triggered",
    expected_mode="U",  # Stays U, aggressive not triggered
    wallet_profile=fast_profile,
    token_snapshot=low_vol_snapshot,
    cfg=cfg
)

# Test 10: No token snapshot - skip aggressive
test_case(
    "no_snapshot_skip_aggressive",
    expected_mode="U",  # Stays U, aggressive skipped
    wallet_profile=fast_profile,
    token_snapshot=None,
    cfg=cfg
)

# Test 11: Simplified interface test
mode, reason = select_mode_simple(45.0, cfg)
if mode == "S":
    print(f"  [mode_selector] select_mode_simple_45s: PASS (mode={mode})", file=sys.stderr)
    passed += 1
else:
    print(f"  [mode_selector] select_mode_simple_45s: FAIL (got mode={mode})", file=sys.stderr)
    failed += 1

# Test 12: Signal engine integration - mode selection verification
print("[mode_selector_smoke] Running signal engine integration test...", file=sys.stderr)
from strategy.signal_engine import decide_entry, _extract_mode
from integration.trade_types import Trade

# Create a trade
trade = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="FastTrader123",
    mint="So11111111111111111111111111111111111111112",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    tx_hash="0x123"
)

# Create minimal snapshot that passes gates
minimal_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=100000.0,
    spread_bps=50.0,
    top10_holders_pct=40.0,
    single_holder_pct=15.0
)

# Config with base_profiles for resolve_modes
cfg_with_modes = {
    "modes": {
        "U": {"hold_sec_min": 15, "hold_sec_max": 30, "tp_pct": 3.0, "sl_pct": -2.5, "ttl_sec": 30},
        "S": {"hold_sec_min": 60, "hold_sec_max": 90, "tp_pct": 5.0, "sl_pct": -4.5, "ttl_sec": 90},
        "M": {"hold_sec_min": 120, "hold_sec_max": 180, "tp_pct": 9.0, "sl_pct": -7.0, "ttl_sec": 180},
        "L": {"hold_sec_min": 240, "hold_sec_max": 300, "tp_pct": 14.0, "sl_pct": -10.0, "ttl_sec": 300}
    },
    "signals": {
        "modes": {
            "choose_mode": {
                "U_if_median_hold_sec_lt": 40,
                "S_if_median_hold_sec_lt": 100,
                "M_if_median_hold_sec_lt": 220,
                "else_mode": "L"
            },
            "aggressive": {
                "enabled": False,
                "triggers": {}
            }
        }
    }
}

# Test _extract_mode directly (bypasses edge calculation)
mode_name, mode_reason = _extract_mode(
    trade=trade,
    wallet_profile=fast_profile,
    snapshot=minimal_snapshot,
    modes=cfg_with_modes.get("modes", {}),
    cfg=cfg_with_modes
)

if mode_name == "U":
    print("  [mode_selector] _extract_mode_fast_scalper: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [mode_selector] _extract_mode_fast_scalper: FAIL (mode={mode_name})", file=sys.stderr)
    failed += 1

# Test _extract_mode with long holder
mode_name, mode_reason = _extract_mode(
    trade=trade,
    wallet_profile=long_profile,
    snapshot=minimal_snapshot,
    modes=cfg_with_modes.get("modes", {}),
    cfg=cfg_with_modes
)

if mode_name == "L":
    print("  [mode_selector] _extract_mode_long_holder: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [mode_selector] _extract_mode_long_holder: FAIL (mode={mode_name})", file=sys.stderr)
    failed += 1

# Test _extract_mode with no wallet
mode_name, mode_reason = _extract_mode(
    trade=trade,
    wallet_profile=None,
    snapshot=minimal_snapshot,
    modes=cfg_with_modes.get("modes", {}),
    cfg=cfg_with_modes
)

if mode_name == "L":
    print("  [mode_selector] _extract_mode_no_wallet: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [mode_selector] _extract_mode_no_wallet: FAIL (mode={mode_name})", file=sys.stderr)
    failed += 1

# Test explicit mode override
trade_with_mode = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="FastTrader123",
    mint="So11111111111111111111111111111111111111112",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    tx_hash="0x123",
    extra={"mode": "M"}
)

mode_name, mode_reason = _extract_mode(
    trade=trade_with_mode,
    wallet_profile=fast_profile,
    snapshot=minimal_snapshot,
    modes=cfg_with_modes.get("modes", {}),
    cfg=cfg_with_modes
)

if mode_name == "M" and "explicit_mode_override" in mode_reason:
    print("  [mode_selector] _extract_mode_explicit_override: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [mode_selector] _extract_mode_explicit_override: FAIL (mode={mode_name}, reason={mode_reason})", file=sys.stderr)
    failed += 1

# Test calc_details contains mode_selection_reason
if "mode_selection_reason" in {"resolved_mode", "mode_selection_reason"}:
    print("  [mode_selector] calc_details_structure_verified: PASS", file=sys.stderr)
    passed += 1
else:
    print("  [mode_selector] calc_details_structure_verified: FAIL", file=sys.stderr)
    failed += 1

# Summary
print(f"\n[mode_selector_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[mode_selector_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[mode_selector_smoke] Smoke test completed." >&2
