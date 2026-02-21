#!/usr/bin/env bash
set -euo pipefail

# scripts/security_gate_smoke.sh
# Smoke test for security gate validation

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 << 'PYTHON_SCRIPT'
"""Smoke test for security gate validation."""

import sys
from integration.gates import _extract_security_data, _security_gate, apply_gates
from integration.token_snapshot_store import TokenSnapshot
from integration.trade_types import Trade
from integration.reject_reasons import (
    HONEYPOT_FAIL,
    FREEZE_AUTHORITY_FAIL,
    MINT_AUTHORITY_FAIL,
    SECURITY_TOP_HOLDERS_FAIL,
)

errors = []

# ============================================
# TEST 1: Good case - all security checks pass
# ============================================
print("TEST 1: Good case - security data passes all checks", file=sys.stderr)

good_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra={"security": {"is_honeypot": False, "freeze_authority": None, "mint_authority": None, "top_holders_pct": 0.5}},
)

is_safe, reason = _extract_security_data(good_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if not is_safe:
    errors.append(f"TEST 1 FAILED: Expected is_safe=True, got False. Reason: {reason}")

if reason is not None:
    errors.append(f"TEST 1 FAILED: Expected reason=None, got '{reason}'")

# ============================================
# TEST 2: Bad case - honeypot detected
# ============================================
print("\nTEST 2: Bad case - honeypot detected", file=sys.stderr)

honeypot_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra={"security": {"is_honeypot": True, "freeze_authority": None, "mint_authority": None, "top_holders_pct": 0.5}},
)

is_safe, reason = _extract_security_data(honeypot_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if is_safe:
    errors.append(f"TEST 2 FAILED: Expected is_safe=False, got True")

if reason != HONEYPOT_FAIL:
    errors.append(f"TEST 2 FAILED: Expected reason='{HONEYPOT_FAIL}', got '{reason}'")

# ============================================
# TEST 3: Bad case - freeze authority enabled
# ============================================
print("\nTEST 3: Bad case - freeze authority enabled", file=sys.stderr)

freeze_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra={"security": {"is_honeypot": False, "freeze_authority": True, "mint_authority": None, "top_holders_pct": 0.5}},
)

is_safe, reason = _extract_security_data(freeze_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if is_safe:
    errors.append(f"TEST 3 FAILED: Expected is_safe=False, got True")

if reason != FREEZE_AUTHORITY_FAIL:
    errors.append(f"TEST 3 FAILED: Expected reason='{FREEZE_AUTHORITY_FAIL}', got '{reason}'")

# ============================================
# TEST 4: Bad case - mint authority enabled
# ============================================
print("\nTEST 4: Bad case - mint authority enabled", file=sys.stderr)

mint_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra={"security": {"is_honeypot": False, "freeze_authority": None, "mint_authority": True, "top_holders_pct": 0.5}},
)

is_safe, reason = _extract_security_data(mint_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if is_safe:
    errors.append(f"TEST 4 FAILED: Expected is_safe=False, got True")

if reason != MINT_AUTHORITY_FAIL:
    errors.append(f"TEST 4 FAILED: Expected reason='{MINT_AUTHORITY_FAIL}', got '{reason}'")

# ============================================
# TEST 5: Bad case - top holders percentage too high
# ============================================
print("\nTEST 5: Bad case - top holders percentage too high", file=sys.stderr)

holders_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra={"security": {"is_honeypot": False, "freeze_authority": None, "mint_authority": None, "top_holders_pct": 75.0}},
)

is_safe, reason = _extract_security_data(holders_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if is_safe:
    errors.append(f"TEST 5 FAILED: Expected is_safe=False, got True")

if reason != SECURITY_TOP_HOLDERS_FAIL:
    errors.append(f"TEST 5 FAILED: Expected reason='{SECURITY_TOP_HOLDERS_FAIL}', got '{reason}'")

# ============================================
# TEST 6: Edge case - no security data (should pass)
# ============================================
print("\nTEST 6: Edge case - no security data (should pass)", file=sys.stderr)

no_security_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    top10_holders_pct=60.0,
    single_holder_pct=20.0,
    extra=None,
)

is_safe, reason = _extract_security_data(no_security_snapshot)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if not is_safe:
    errors.append(f"TEST 6 FAILED: Expected is_safe=True (no security data), got False")

if reason is not None:
    errors.append(f"TEST 6 FAILED: Expected reason=None (no security data), got '{reason}'")

# ============================================
# TEST 7: Edge case - null snapshot (should pass)
# ============================================
print("\nTEST 7: Edge case - null snapshot (should pass)", file=sys.stderr)

is_safe, reason = _extract_security_data(None)
print(f"  is_safe={is_safe}, reason={reason}", file=sys.stderr)

if not is_safe:
    errors.append(f"TEST 7 FAILED: Expected is_safe=True (null snapshot), got False")

if reason is not None:
    errors.append(f"TEST 7 FAILED: Expected reason=None (null snapshot), got '{reason}'")

# ============================================
# TEST 8: Integration test - apply_gates with security data
# ============================================
print("\nTEST 8: Integration test - apply_gates with security data", file=sys.stderr)

trade = Trade(
    ts="2024-01-15 10:00:00",
    wallet="7nYhPEv7z3ZN2cNVPzZ8xqZQ8QpV4z3g6v5h2w9x8y0z",
    mint="So11111111111111111111111111111111111111112",
    side="BUY",
    price=100.0,
    size_usd=100.0,
    platform="raydium",
    tx_hash="5x5t5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g",
    liquidity_usd=50000.0,
    volume_24h_usd=200000.0,
    spread_bps=120.0,
    honeypot_pass=True,
    wallet_roi_30d_pct=25.0,
    wallet_winrate_30d=0.80,
    wallet_trades_30d=100,
)

cfg = {
    "token_profile": {
        "gates": {
            "min_liquidity_usd": 10000.0,
            "min_volume_24h_usd": 50000.0,
            "max_spread_bps": 200.0,
        },
        "security": {
            "enabled": True,
        },
    },
    "signals": {
        "hard_filters": {},
    },
}

decision = apply_gates(cfg=cfg, trade=trade, snapshot=good_snapshot)
print(f"  Decision: passed={decision.passed}, reasons={decision.reasons}", file=sys.stderr)

if not decision.passed:
    errors.append(f"TEST 8 FAILED: Expected passed=True, got False. Reasons: {decision.reasons}")

# ============================================
# Final result
# ============================================
if errors:
    print("\nERRORS:", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

print("\n[security_gate_smoke] OK ✅", file=sys.stdout)
PYTHON_SCRIPT
