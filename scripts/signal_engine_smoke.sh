#!/usr/bin/env bash
set -euo pipefail

# scripts/signal_engine_smoke.sh
# Smoke test for PR-S.1 Signal Engine v1 - decide_entry function

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 << 'PYTHON_SCRIPT'
"""Smoke test for signal_engine.decide_entry function."""

import sys
import yaml

# Import from strategy.signal_engine
from strategy.signal_engine import decide_entry, SignalDecision
from integration.trade_types import Trade
from integration.token_snapshot_store import TokenSnapshot
from integration.wallet_profile_store import WalletProfile
from integration.reject_reasons import MIN_LIQUIDITY_FAIL

# Load base config
with open("strategy/config/params_base.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# Add min_edge_bps for the signal engine
cfg["min_edge_bps"] = 0

# Move modes to expected location (compute_edge_bps expects cfg["modes"])
# The YAML has modes at cfg["signals"]["modes"]["base_profiles"]
if "signals" in cfg and "modes" in cfg["signals"]:
    signals_modes = cfg["signals"]["modes"]
    if "base_profiles" in signals_modes:
        cfg["modes"] = signals_modes["base_profiles"]

errors = []

# ============================================
# TEST 1: Good case - passes all gates, positive edge
# ============================================
print("TEST 1: Good case - trade with high liquidity and positive edge", file=sys.stderr)

good_trade = Trade(
    ts="2024-01-15 10:00:00",
    wallet="7nYhPEv7z3ZN2cNVPzZ8xqZQ8QpV4z3g6v5h2w9x8y0z",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    side="BUY",
    price=100.0,
    size_usd=100.0,
    platform="raydium",
    tx_hash="5x5t5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g5h5g",
    liquidity_usd=50000.0,
    volume_24h_usd=100000.0,
    spread_bps=10,  # Low spread for positive edge
    honeypot_pass=True,
    wallet_roi_30d_pct=25.0,
    wallet_winrate_30d=0.80,  # Higher winrate for positive edge
    wallet_trades_30d=100,
)

good_snapshot = TokenSnapshot(
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    liquidity_usd=50000.0,
    volume_24h_usd=100000.0,
    spread_bps=10,  # Low spread
    top10_holders_pct=50.0,
    single_holder_pct=20.0,
)

good_wallet = WalletProfile(
    wallet="7nYhPEv7z3ZN2cNVPzZ8xqZQ8QpV4z3g6v5h2w9x8y0z",
    tier="tier1",
    roi_30d_pct=25.0,
    winrate_30d=0.80,  # Higher winrate
    trades_30d=100,
    median_hold_sec=25.0,
    avg_trade_size_sol=1.5,
)

good_decision = decide_entry(
    trade=good_trade,
    snapshot=good_snapshot,
    wallet_profile=good_wallet,
    cfg=cfg,
)

print(f"  Decision: should_enter={good_decision.should_enter}, reason={good_decision.reason}", file=sys.stderr)
print(f"  Mode: {good_decision.mode}, edge_bps: {good_decision.edge_bps}", file=sys.stderr)

if not good_decision.should_enter:
    errors.append(f"TEST 1 FAILED: Expected should_enter=True, got False. Reason: {good_decision.reason}")

if good_decision.reason not in ("entry_ok", None):
    errors.append(f"TEST 1 FAILED: Expected reason='entry_ok' or None, got '{good_decision.reason}'")

# ============================================
# TEST 2: Bad case - low liquidity fails gate
# ============================================
print("\nTEST 2: Bad case - trade with low liquidity (should fail gates)", file=sys.stderr)

bad_trade = Trade(
    ts="2024-01-15 10:00:00",
    wallet="7nYhPEv7z3ZN2cNVPzZ8xqZQ8QpV4z3g6v5h2w9x8y0z",
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    side="BUY",
    price=100.0,
    size_usd=100.0,
    platform="raydium",
    tx_hash="6y6u6i6o6p6q6r6s6t6u6v6w6x6y6z6a6b6c6d6e6f6g6h6i",
    # Low liquidity - below min_liquidity_usd=15000 threshold
    liquidity_usd=5000.0,
    volume_24h_usd=100000.0,
    spread_bps=50,
    honeypot_pass=True,
    wallet_roi_30d_pct=25.0,
    wallet_winrate_30d=0.65,
    wallet_trades_30d=100,
)

bad_snapshot = TokenSnapshot(
    mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    liquidity_usd=5000.0,  # Below threshold
    volume_24h_usd=100000.0,
    spread_bps=50,
    top10_holders_pct=50.0,
    single_holder_pct=20.0,
)

bad_wallet = WalletProfile(
    wallet="7nYhPEv7z3ZN2cNVPzZ8xqZQ8QpV4z3g6v5h2w9x8y0z",
    tier="tier1",
    roi_30d_pct=25.0,
    winrate_30d=0.65,
    trades_30d=100,
    median_hold_sec=25.0,
    avg_trade_size_sol=1.5,
)

bad_decision = decide_entry(
    trade=bad_trade,
    snapshot=bad_snapshot,
    wallet_profile=bad_wallet,
    cfg=cfg,
)

print(f"  Decision: should_enter={bad_decision.should_enter}, reason={bad_decision.reason}", file=sys.stderr)

if bad_decision.should_enter:
    errors.append(f"TEST 2 FAILED: Expected should_enter=False, got True")

if bad_decision.reason is None or MIN_LIQUIDITY_FAIL not in str(bad_decision.reason):
    errors.append(f"TEST 2 FAILED: Expected reason to contain '{MIN_LIQUIDITY_FAIL}', got '{bad_decision.reason}'")

# ============================================
# Final result
# ============================================
if errors:
    print("\nERRORS:", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

print("\n[signal_engine_smoke] OK ✅", file=sys.stdout)
PYTHON_SCRIPT
