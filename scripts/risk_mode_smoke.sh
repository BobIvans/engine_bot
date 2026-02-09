#!/usr/bin/env bash
# scripts/risk_mode_smoke.sh
# Smoke test for Mode-Aware Risk Limits (PR-C.2)
# Tests mode-specific position and exposure limits

set -e

# Get the directory where this script is located and cd to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
cd "$PROJECT_ROOT"

# Python smoke test for mode-specific risk limits
python3 << 'PYTHON_EOF'
import sys
sys.path.insert(0, '.')

from integration.portfolio_stub import PortfolioStub
from integration.trade_types import Trade
from integration.reject_reasons import RISK_MODE_LIMIT
from strategy.risk_engine import apply_risk_limits

def test_scenario_1_max_open_positions():
    """Scenario 1: Max Open Positions per Mode"""
    # Config: max_open: 1 for mode "M"
    cfg = {
        "risk": {
            "limits": {
                "modes": {
                    "M": {
                        "max_open": 1
                    }
                }
            }
        }
    }
    
    # Portfolio: active_counts_by_mode["M"] = 1
    portfolio = PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=11000.0,
        open_positions=1,
        active_counts_by_mode={"M": 1}
    )
    
    # Trade: extra.mode = "M"
    trade = Trade(
        ts="2026-01-05 10:00:00",
        wallet="test_wallet",
        mint="test_mint",
        side="buy",
        price=1.0,
        size_usd=100.0,
        extra={"mode": "M"}
    )
    
    allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
    
    if not allowed and reason == RISK_MODE_LIMIT:
        return True, None
    else:
        return False, f"Expected RISK_MODE_LIMIT, got allowed={allowed}, reason={reason}"


def test_scenario_2_max_exposure():
    """Scenario 2: Max Exposure per Mode"""
    # Config: max_exposure_usd: 100 for mode "M"
    cfg = {
        "risk": {
            "limits": {
                "modes": {
                    "M": {
                        "max_exposure_usd": 100
                    }
                }
            }
        }
    }
    
    # Portfolio: exposure_by_mode["M"] = 100
    portfolio = PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=11000.0,
        open_positions=0,
        exposure_by_mode={"M": 100.0}
    )
    
    # Trade: size_usd = 50, extra.mode = "M"
    trade = Trade(
        ts="2026-01-05 10:00:00",
        wallet="test_wallet",
        mint="test_mint",
        side="buy",
        price=1.0,
        size_usd=50.0,
        extra={"mode": "M"}
    )
    
    allowed, reason = apply_risk_limits(trade=trade, signal=None, portfolio=portfolio, cfg=cfg)
    
    if not allowed and reason == RISK_MODE_LIMIT:
        return True, None
    else:
        return False, f"Expected RISK_MODE_LIMIT, got allowed={allowed}, reason={reason}"


def main():
    errors = []
    
    # Run Scenario 1
    try:
        success, error = test_scenario_1_max_open_positions()
        if not success:
            errors.append(f"Scenario 1 failed: {error}")
    except Exception as e:
        errors.append(f"Scenario 1 exception: {e}")
    
    # Run Scenario 2
    try:
        success, error = test_scenario_2_max_exposure()
        if not success:
            errors.append(f"Scenario 2 failed: {error}")
    except Exception as e:
        errors.append(f"Scenario 2 exception: {e}")
    
    if errors:
        print("[risk_mode_smoke] FAIL: " + "; ".join(errors))
        sys.exit(1)
    else:
        print("[risk_mode_smoke] OK ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
PYTHON_EOF

exit $?
