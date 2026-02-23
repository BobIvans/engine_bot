#!/bin/bash
# scripts/risk_aggr_smoke.sh
# Smoke test for Aggressive Risk Gates & Kill-Switch (PR-E.2.1)

set -e

GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT_DIR

echo "[overlay_lint] running risk aggr smoke..." >&2

python3 <<PYEOF
import os
import sys
import yaml

ROOT_DIR = os.environ.get("ROOT_DIR", ".")
sys.path.insert(0, ROOT_DIR)

from strategy.risk_engine import (
    AggressiveSafetyContext,
    passes_safety_filters,
    allow_aggressive_trade,
)

# Load config with restrictive thresholds
cfg_path = os.path.join(ROOT_DIR, "integration/fixtures/config/risk_aggr_blocked.yaml")
with open(cfg_path, "r") as f:
    cfg = yaml.safe_load(f)

print("[risk_aggr_smoke] Testing aggressive risk gates...")

# Test 1: Standard token with low liquidity should be BLOCKED
# Config requires \$1M liquidity, but token has \$50k
ctx1 = AggressiveSafetyContext(
    wallet_winrate_30d=0.70,
    wallet_roi_30d_pct=0.30,
    token_liquidity_usd=50000,  # \$50k - below \$1M threshold
    token_top10_holders_pct=0.60,
    daily_loss_pct=-0.02,
    aggr_trades_today=2,
    aggr_open_positions=1,
)

result1 = passes_safety_filters(ctx1, cfg)
assert result1 is False, f"Test 1: Token with \$50k liquidity should be blocked, got {result1}"
print("  Test 1: Token with \$50k liquidity BLOCKED (requires \$1M) - PASS")

# Test 2: Super token but weak wallet should be BLOCKED
# Token has \$2M liquidity, but wallet has 55% winrate (requires 60%)
ctx2 = AggressiveSafetyContext(
    wallet_winrate_30d=0.55,  # Below 60% threshold
    wallet_roi_30d_pct=0.30,
    token_liquidity_usd=2000000,  # \$2M - above \$1M threshold
    token_top10_holders_pct=0.60,
    daily_loss_pct=-0.02,
    aggr_trades_today=2,
    aggr_open_positions=1,
)

result2 = passes_safety_filters(ctx2, cfg)
assert result2 is False, f"Test 2: Weak wallet (55% winrate) should be blocked, got {result2}"
print("  Test 2: Weak wallet (55% winrate) BLOCKED (requires 60%) - PASS")

# Test 3: High daily loss should BLOCK aggressive mode
ctx3 = AggressiveSafetyContext(
    wallet_winrate_30d=0.70,
    wallet_roi_30d_pct=0.30,
    token_liquidity_usd=2000000,
    token_top10_holders_pct=0.60,
    daily_loss_pct=-0.06,  # -6% daily loss, above 5% threshold
    aggr_trades_today=2,
    aggr_open_positions=1,
)

result3 = passes_safety_filters(ctx3, cfg)
assert result3 is False, f"Test 3: High daily loss (-6%) should be blocked, got {result3}"
print("  Test 3: High daily loss (-6%) BLOCKED (threshold 5%) - PASS")

# Test 4: Too many aggressive trades today should BLOCK
ctx4 = AggressiveSafetyContext(
    wallet_winrate_30d=0.70,
    wallet_roi_30d_pct=0.30,
    token_liquidity_usd=2000000,
    token_top10_holders_pct=0.60,
    daily_loss_pct=-0.02,
    aggr_trades_today=11,  # Above limit of 10
    aggr_open_positions=1,
)

result4 = passes_safety_filters(ctx4, cfg)
assert result4 is False, f"Test 4: Too many aggr trades (11) should be blocked, got {result4}"
print("  Test 4: Too many aggr trades today (11) BLOCKED (limit 10) - PASS")

# Test 5: Valid Super Token + Strong Wallet should be ALLOWED
ctx5 = AggressiveSafetyContext(
    wallet_winrate_30d=0.70,  # Above 60% threshold
    wallet_roi_30d_pct=0.30,  # Above 25% threshold
    token_liquidity_usd=2000000,  # Above \$1M threshold
    token_top10_holders_pct=0.60,  # Below 70% threshold
    daily_loss_pct=-0.02,  # Below 5% threshold
    aggr_trades_today=5,  # Below 10 limit
    aggr_open_positions=2,  # Below 3 limit
)

result5 = passes_safety_filters(ctx5, cfg)
assert result5 is True, f"Test 5: Valid candidate should be allowed, got {result5}"
print("  Test 5: Super token + Strong wallet ALLOWED - PASS")

# Test 6: Test allow_aggressive_trade with reason
allowed, reason = allow_aggressive_trade(ctx1, cfg)
assert allowed is False, "Test 6: Should not allow weak token"
assert "liquidity" in reason.lower(), f"Reason should mention liquidity: {reason}"
print(f"  Test 6: allow_aggressive_trade reason: '{reason}' - PASS")

# Test 7: Test allow_aggressive_trade with valid context
allowed7, reason7 = allow_aggressive_trade(ctx5, cfg)
assert allowed7 is True, "Test 7: Should allow strong candidate"
assert "allowed" in reason7.lower(), f"Reason should mention allowed: {reason7}"
print(f"  Test 7: allow_aggressive_trade reason: '{reason7}' - PASS")

# Test 8: Fail-safe - missing data should return False
ctx8 = AggressiveSafetyContext(
    wallet_winrate_30d=None,  # Missing data
    wallet_roi_30d_pct=0.30,
    token_liquidity_usd=2000000,
    token_top10_holders_pct=0.60,
    daily_loss_pct=-0.02,
    aggr_trades_today=2,
    aggr_open_positions=1,
)

result8 = passes_safety_filters(ctx8, cfg)
assert result8 is False, "Test 8: Missing wallet data should be blocked (fail-safe)"
print("  Test 8: Missing data (fail-safe) BLOCKED - PASS")

print("\\n[risk_aggr_smoke] All aggressive risk gate tests passed!")
PYEOF

echo -e "${GREEN}[risk_aggr_smoke] OK ✅${NC}" >&2
exit 0
