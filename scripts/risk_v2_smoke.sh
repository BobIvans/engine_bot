#!/bin/bash
# scripts/risk_v2_smoke.sh
# PR-B.5 Risk Engine v2 - Fractional Kelly & Portfolio Exposure Smoke Test

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[risk_v2_smoke] Starting Risk Engine v2 smoke test..." >&2

# Python test script
python3 << 'PYTHON_TEST'
import sys
from collections import defaultdict

# Add root to path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from integration.portfolio_stub import PortfolioStub
from integration.trade_types import Trade
from strategy.risk_engine import compute_position_size_usd, _check_exposure_limits, apply_risk_limits
from integration.reject_reasons import RISK_MAX_EXPOSURE

# Test counters
passed = 0
failed = 0

# Configuration for Kelly sizing tests
kelly_cfg = {
    "risk": {
        "sizing": {
            "method": "fractional_kelly",
            "kelly_fraction": 0.25,
            "min_pos_pct": 0.5,
            "max_pos_pct": 15.0,  # Allow up to 15% (enough for 10% Kelly)
            "fixed_pct_of_bankroll": 1.0,
            "proxy_edge": {
                "enabled": True,
                "p_model_baseline": 0.55,
                "edge_per_0_01_p": 1.5
            }
        },
        "limits": {
            "max_exposure_per_token_pct": 10.0  # 10% of equity max per token
        }
    }
}

# Configuration for fixed sizing (fallback)
fixed_cfg = {
    "risk": {
        "sizing": {
            "method": "fixed_pct",
            "fixed_pct_of_bankroll": 1.0,
            "min_pos_pct": 0.5,
            "max_pos_pct": 2.0
        },
        "limits": {}
    }
}

print("[risk_v2_smoke] Running Fractional Kelly sizing tests...", file=sys.stderr)

# Test 1: Kelly sizing with p_model=0.6, tp=0.1, sl=-0.05 (b=2)
# f_star = (0.6 * (2 + 1) - 1) / 2 = (1.8 - 1) / 2 = 0.4 = 40%
# Kelly size = 40% * 0.25 = 10% = $1000
# Within min=0.5% ($50) and max=15% ($1500), so result = $1000
portfolio = PortfolioStub(
    equity_usd=10000.0,
    peak_equity_usd=10500.0,
    open_positions=0,
    exposure_by_token=defaultdict(float)
)

size = compute_position_size_usd(
    portfolio=portfolio,
    cfg=kelly_cfg,
    p_model=0.6,
    estimated_payoff=2.0  # tp=0.1 / abs(sl=-0.05) = 2
)

# Expected: 10% of $10000 = $1000
expected_size = 1000.0
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] kelly_sizing_basic: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] kelly_sizing_basic: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

# Test 2: Kelly sizing with high edge (p_model=0.75, b=2)
# f_star = (0.75 * 3 - 1) / 2 = (2.25 - 1) / 2 = 0.625 = 62.5%
# Kelly size = 62.5% * 0.25 = 15.625%
# With max_pos_pct=15%, should be clamped to 15% = $1500
size = compute_position_size_usd(
    portfolio=portfolio,
    cfg=kelly_cfg,
    p_model=0.75,
    estimated_payoff=2.0
)

expected_size = 1500.0  # 15% of $10000 (clamped)
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] kelly_sizing_clamped: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] kelly_sizing_clamped: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

# Test 3: Kelly with low edge (p_model=0.52, b=2)
# f_star = (0.52 * 3 - 1) / 2 = (1.56 - 1) / 2 = 0.28 = 28%
# Kelly size = 28% * 0.25 = 7% = $700
size = compute_position_size_usd(
    portfolio=portfolio,
    cfg=kelly_cfg,
    p_model=0.52,
    estimated_payoff=2.0
)

expected_size = 700.0  # 7% of $10000
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] kelly_sizing_low_edge: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] kelly_sizing_low_edge: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

# Test 4: Fixed percentage sizing (fallback)
size = compute_position_size_usd(
    portfolio=portfolio,
    cfg=fixed_cfg,
    p_model=0.6
)

expected_size = 100.0  # 1% of $10000
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] fixed_sizing_fallback: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] fixed_sizing_fallback: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

print("[risk_v2_smoke] Running exposure limit tests...", file=sys.stderr)

# Test 5: Exposure limit - token within limit
trade = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="TestWallet",
    mint="TokenA",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    tx_hash="0x123"
)

portfolio_with_exposure = PortfolioStub(
    equity_usd=10000.0,
    peak_equity_usd=10500.0,
    open_positions=2,
    exposure_by_token=defaultdict(float, {"TokenA": 500.0})  # $500 existing exposure
)

# Max exposure = 10% of $10000 = $1000
# Current = $500, so should allow more
allowed, reason = _check_exposure_limits(
    trade=trade,
    portfolio=portfolio_with_exposure,
    cfg=kelly_cfg
)

if allowed and reason is None:
    print(f"  [risk_v2] exposure_under_limit: PASS (allowed={allowed})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] exposure_under_limit: FAIL (allowed={allowed}, reason={reason})", file=sys.stderr)
    failed += 1

# Test 6: Exposure limit - token at limit
portfolio_at_limit = PortfolioStub(
    equity_usd=10000.0,
    peak_equity_usd=10500.0,
    open_positions=2,
    exposure_by_token=defaultdict(float, {"TokenA": 1000.0})  # $1000 = 10% limit
)

allowed, reason = _check_exposure_limits(
    trade=trade,
    portfolio=portfolio_at_limit,
    cfg=kelly_cfg
)

if not allowed and reason == RISK_MAX_EXPOSURE:
    print(f"  [risk_v2] exposure_at_limit: PASS (rejected with {reason})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] exposure_at_limit: FAIL (allowed={allowed}, reason={reason})", file=sys.stderr)
    failed += 1

# Test 7: Exposure limit - token exceeding limit
portfolio_exceeding = PortfolioStub(
    equity_usd=10000.0,
    peak_equity_usd=10500.0,
    open_positions=2,
    exposure_by_token=defaultdict(float, {"TokenA": 1200.0})  # $1200 > 10% limit
)

allowed, reason = _check_exposure_limits(
    trade=trade,
    portfolio=portfolio_exceeding,
    cfg=kelly_cfg
)

if not allowed and reason == RISK_MAX_EXPOSURE:
    print(f"  [risk_v2] exposure_exceeding_limit: PASS (rejected with {reason})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] exposure_exceeding_limit: FAIL (allowed={allowed}, reason={reason})", file=sys.stderr)
    failed += 1

# Test 8: Position sizing respects remaining exposure
# Portfolio has $500 of TokenA, max is $1000, so remaining is $500
# Kelly calculation gives $1000 for p_model=0.6, but remaining is $500
size = compute_position_size_usd(
    portfolio=portfolio_with_exposure,
    cfg=kelly_cfg,
    p_model=0.6,
    estimated_payoff=2.0,
    trade_mint="TokenA"
)

# Expected: min($1000 Kelly, $500 remaining) = $500
expected_size = 500.0
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] sizing_respects_exposure: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] sizing_respects_exposure: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

# Test 9: apply_risk_limits integration
print("[risk_v2_smoke] Running apply_risk_limits integration test...", file=sys.stderr)

# This trade should pass all risk checks
trade_ok = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="TestWallet",
    mint="TokenB",
    side="BUY",
    price=1.0,
    size_usd=50.0,
    tx_hash="0x456"
)

allowed, reason = apply_risk_limits(
    trade=trade_ok,
    signal=None,
    portfolio=portfolio,
    cfg=kelly_cfg
)

if allowed and reason is None:
    print(f"  [risk_v2] apply_risk_limits_ok: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] apply_risk_limits_ok: FAIL (allowed={allowed}, reason={reason})", file=sys.stderr)
    failed += 1

# This trade should fail exposure check
trade_reject = Trade(
    ts="2024-01-01T00:00:00Z",
    wallet="TestWallet",
    mint="TokenA",
    side="BUY",
    price=1.0,
    size_usd=50.0,
    tx_hash="0x789"
)

allowed, reason = apply_risk_limits(
    trade=trade_reject,
    signal=None,
    portfolio=portfolio_at_limit,  # TokenA at $1000 limit
    cfg=kelly_cfg
)

if not allowed and reason == RISK_MAX_EXPOSURE:
    print(f"  [risk_v2] apply_risk_limits_exposure: PASS (rejected with {reason})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] apply_risk_limits_exposure: FAIL (allowed={allowed}, reason={reason})", file=sys.stderr)
    failed += 1

# Test 10: exposure_by_token field exists in PortfolioStub
if hasattr(portfolio, 'exposure_by_token'):
    print(f"  [risk_v2] exposure_by_token_exists: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] exposure_by_token_exists: FAIL", file=sys.stderr)
    failed += 1

# Test 11: Kelly formula verification
# With p_model=0.6, b=2, kf=0.25:
# f_star = (0.6 * 3 - 1) / 2 = 0.4
# kelly_pct = 0.4 * 0.25 * 100 = 10%
size = compute_position_size_usd(
    portfolio=portfolio,
    cfg=kelly_cfg,
    p_model=0.6,
    estimated_payoff=2.0
)
expected_size = 1000.0  # 10% of $10000
if abs(size - expected_size) < 1.0:
    print(f"  [risk_v2] kelly_formula_verification: PASS (size=${size:.2f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [risk_v2] kelly_formula_verification: FAIL (got ${size:.2f}, expected ${expected_size:.2f})", file=sys.stderr)
    failed += 1

# Summary
print(f"\n[risk_v2_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[risk_v2_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[risk_v2_smoke] Smoke test completed." >&2
