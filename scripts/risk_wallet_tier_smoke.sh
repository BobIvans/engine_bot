#!/bin/bash
# scripts/risk_wallet_tier_smoke.sh
# Smoke test for wallet tier risk limit logic (PR-C.1)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Python smoke test for wallet tier limits
python3 << 'PYTHON_SCRIPT'
"""Wallet Tier Risk Limit Smoke Test"""
import sys
from collections import defaultdict

# Import the function under test
from strategy.risk_engine import _check_tier_limits
from integration.portfolio_stub import PortfolioStub
from integration.trade_types import Trade
from integration.reject_reasons import RISK_WALLET_TIER_LIMIT

def run_tests():
    """Test three wallet tier limit scenarios."""
    errors = []
    
    # =========================================================================
    # Test 1: Tier Limit Not Exceeded (Pass)
    # =========================================================================
    cfg = {
        "risk": {
            "limits": {
                "tier_limits": {
                    "tier2": {
                        "max_open_positions": 1
                    }
                }
            }
        }
    }
    
    portfolio = PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=10000.0,
        open_positions=0,
        day_pnl_usd=0.0,
        consecutive_losses=0,
        cooldown_until=0.0,
        active_counts_by_tier={"tier2": 0}  # 0 active positions in tier2
    )
    
    trade = Trade(
        ts="2026-01-01 12:00:00",
        wallet="test_wallet",
        mint="test_mint",
        side="buy",
        price=1.0,
        size_usd=100.0,
        extra={"wallet_tier": "tier2"}
    )
    
    allowed, reason = _check_tier_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not (allowed is True and reason is None):
        errors.append(
            f"Test 1 FAILED: Expected (True, None), got ({allowed}, {reason})"
        )
    else:
        print("[risk_wallet_tier_smoke] Test 1 PASSED: Tier limit not exceeded", file=sys.stderr)
    
    # =========================================================================
    # Test 2: Tier Limit Exceeded (Reject)
    # =========================================================================
    cfg = {
        "risk": {
            "limits": {
                "tier_limits": {
                    "tier2": {
                        "max_open_positions": 1
                    }
                }
            }
        }
    }
    
    portfolio = PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=10000.0,
        open_positions=1,
        day_pnl_usd=0.0,
        consecutive_losses=0,
        cooldown_until=0.0,
        active_counts_by_tier={"tier2": 1}  # 1 active position = at limit
    )
    
    trade = Trade(
        ts="2026-01-01 12:00:00",
        wallet="test_wallet",
        mint="test_mint",
        side="buy",
        price=1.0,
        size_usd=100.0,
        extra={"wallet_tier": "tier2"}
    )
    
    allowed, reason = _check_tier_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not (allowed is False and reason == RISK_WALLET_TIER_LIMIT):
        errors.append(
            f"Test 2 FAILED: Expected (False, '{RISK_WALLET_TIER_LIMIT}'), got ({allowed}, {reason})"
        )
    else:
        print("[risk_wallet_tier_smoke] Test 2 PASSED: Tier limit exceeded correctly rejected", file=sys.stderr)
    
    # =========================================================================
    # Test 3: Different Tier (Pass)
    # =========================================================================
    cfg = {
        "risk": {
            "limits": {
                "tier_limits": {
                    "tier1": {
                        "max_open_positions": 5
                    }
                }
            }
        }
    }
    
    portfolio = PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=10000.0,
        open_positions=1,
        day_pnl_usd=0.0,
        consecutive_losses=0,
        cooldown_until=0.0,
        active_counts_by_tier={"tier2": 1, "tier1": 0}  # tier2 at limit, tier1 at 0
    )
    
    trade = Trade(
        ts="2026-01-01 12:00:00",
        wallet="test_wallet",
        mint="test_mint",
        side="buy",
        price=1.0,
        size_usd=100.0,
        extra={"wallet_tier": "tier1"}
    )
    
    allowed, reason = _check_tier_limits(trade=trade, portfolio=portfolio, cfg=cfg)
    if not (allowed is True and reason is None):
        errors.append(
            f"Test 3 FAILED: Expected (True, None), got ({allowed}, {reason})"
        )
    else:
        print("[risk_wallet_tier_smoke] Test 3 PASSED: Different tier allowed correctly", file=sys.stderr)
    
    # =========================================================================
    # Report results
    # =========================================================================
    if errors:
        for err in errors:
            print(f"[risk_wallet_tier_smoke] ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print("[risk_wallet_tier_smoke] OK ✅", file=sys.stderr)
        sys.exit(0)

if __name__ == "__main__":
    run_tests()
PYTHON_SCRIPT

exit $?
