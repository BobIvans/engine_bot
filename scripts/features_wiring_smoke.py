#!/usr/bin/env python3
"""Smoke test for Feature Wiring (PR-C.6).

Tests that ConcreteFeatureBuilder correctly transforms domain objects
into flat feature vectors for the unified decision formula.

Usage:
    python scripts/features_wiring_smoke.py
    bash scripts/features_wiring_smoke.sh

Exit codes:
    - 0: All test cases passed
    - 1: One or more test cases failed
"""

import csv
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.features.builder import ConcreteFeatureBuilder, build_feature_vector
from strategy.logic import WalletProfile, TokenSnapshot, PolymarketSnapshot


def run_smoke_tests():
    """Run feature wiring smoke tests from CSV fixture."""
    script_dir = Path(__file__).parent
    csv_path = script_dir / ".." / "integration" / "fixtures" / "features" / "wiring.csv"
    
    print("[features_wiring_smoke] Starting smoke tests...", file=sys.stderr)
    
    all_passed = True
    test_count = 0
    passed_count = 0
    
    try:
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                test_count += 1
                case_id = row["case_id"]
                
                # Build domain objects from CSV
                wallet = WalletProfile(
                    wallet_address=row["wallet_addr"],
                    winrate=float(row["w_winrate"]),
                    roi_mean=float(row["w_roi"]),
                    trade_count=int(row["w_trades"]),
                    pnl_ratio=float(row.get("w_pnl", 1.0)),
                    avg_holding_time_sec=float(row.get("w_hold", 300)),
                    smart_money_score=float(row.get("w_sm_score", 0.5)),
                )
                
                token = TokenSnapshot(
                    token_address=row["token_addr"],
                    symbol=row["symbol"],
                    liquidity_usd=float(row["liq_usd"]),
                    volume_24h=float(row["vol_24h"]),
                    price=float(row["price"]),
                    holder_count=int(row.get("holders", 100)),
                )
                
                polymarket = PolymarketSnapshot(
                    event_id=row.get("pm_event", "EVT001"),
                    event_title=row.get("pm_title", "Test Event"),
                    outcome=row.get("pm_outcome", "Yes"),
                    probability=float(row["pm_prob"]),
                    volume_usd=float(row.get("pm_vol", 0)),
                    liquidity_usd=float(row.get("pm_liq", 0)),
                    bullish_score=float(row["pm_bullish"]),
                )
                
                # Build feature vector
                builder = ConcreteFeatureBuilder(allow_unknown=True)
                features = builder.build(wallet=wallet, token=token, polymarket=polymarket)
                
                # Verify expected features are present
                expected_features = [
                    "w_roi_30d", "w_winrate_30d", "w_log_trades",
                    "m_ret_1m", "m_ret_5m", "m_vol_5m", "m_log_liq",
                    "pm_bullish", "pm_risk", "interaction_score"
                ]
                
                all_present = all(k in features.features for k in expected_features)
                
                if all_present:
                    # Verify interaction_score = w_winrate * pm_bullish
                    expected_interaction = wallet.winrate * polymarket.bullish_score
                    actual_interaction = features.get("interaction_score")
                    
                    if abs(actual_interaction - expected_interaction) < 0.001:
                        passed = True
                        status = "PASS"
                    else:
                        passed = False
                        status = f"FAIL (interaction mismatch: {actual_interaction} vs {expected_interaction})"
                else:
                    passed = False
                    status = "FAIL (missing features)"
                
                print(f"[features_wiring_smoke] Testing {case_id}... {status}", file=sys.stderr)
                
                if passed:
                    passed_count += 1
                else:
                    all_passed = False
    
    except FileNotFoundError:
        print(f"[features_wiring_smoke] ERROR: CSV file not found at {csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[features_wiring_smoke] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Final result
    if all_passed:
        print(f"[features_wiring_smoke] OK ({passed_count}/{test_count} cases passed)", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"[features_wiring_smoke] FAILED ({passed_count}/{test_count} cases passed)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_tests()
