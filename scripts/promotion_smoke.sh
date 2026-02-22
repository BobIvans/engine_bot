#!/usr/bin/env bash
set -eo pipefail
# Smoke test for PR-H.3 Wallet Pruning & Promotion Logic.
# Tests the daily_prune_and_promote() pure function and integration stage.

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from script
project_root="$(dirname "$SCRIPT_DIR")"

echo "project_root: $project_root" >&2

# Add project to PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}:$project_root"

# Import the promotion module
python3 << 'PYTHON_IMPORT'
import sys

def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

def test_prune_reasons_known():
    """Test 1: Verify prune reasons are known."""
    log("[promotion_smoke] Testing prune reasons are known...")
    
    from strategy.promotion import (
        daily_prune_and_promote,
        PromotionParams,
        WalletProfileInput,
    )
    from integration.reject_reasons import (
        WALLET_WINRATE_7D_LOW,
        WALLET_TRADES_7D_LOW,
        WALLET_ROI_7D_LOW,
        assert_reason_known,
    )
    
    reasons = [WALLET_WINRATE_7D_LOW, WALLET_TRADES_7D_LOW, WALLET_ROI_7D_LOW]
    for r in reasons:
        assert_reason_known(r)
        log(f"[promotion_smoke] {r} is known reason")
    
    log("[promotion_smoke] Test 1 PASSED: All prune reasons known")
    return True

def test_basic_pruning():
    """Test 2: Basic pruning logic with single low-winrate wallet."""
    log("[promotion_smoke] Testing basic pruning logic...")
    
    from strategy.promotion import (
        daily_prune_and_promote,
        PromotionParams,
        WalletProfileInput,
    )
    from integration.reject_reasons import (
        WALLET_WINRATE_7D_LOW,
        assert_reason_known,
    )
    
    params = PromotionParams(
        prune_winrate_7d_min=0.55,
        prune_trades_7d_min=8,
        prune_roi_7d_min=-0.10,
        promote_winrate_30d_min=0.62,
        promote_roi_30d_min=0.18,
        promote_trades_30d_min=45,
        max_candidates_to_promote=30,
    )
    
    active_wallets = [
        WalletProfileInput(
            wallet="wallet_low_winrate",
            winrate_7d=0.40,
            trades_7d=10,
            roi_7d=0.05,
            winrate_30d=0.55,
            roi_30d=0.10,
            trades_30d=100,
        ),
        WalletProfileInput(
            wallet="wallet_good",
            trades_7d=15,
            roi_7d=0.12,
            winrate_30d=0.70,
            roi_30d=0.25,
            trades_30d=120,
        ),
    ]
    
    candidates = []
    
    remaining, pruned = daily_prune_and_promote(active_wallets, candidates, params)
    
    # Should have 1 remaining wallet
    assert len(remaining) == 1, f"Expected 1 remaining, got {len(remaining)}"
    assert remaining[0].wallet == "wallet_good", f"Expected wallet_good to remain"
    
    # Should have 1 pruned wallet with correct reason
    assert len(pruned) == 1, f"Expected 1 pruned, got {len(pruned)}"
    assert pruned[0]["reason"] == WALLET_WINRATE_7D_LOW, f"Wrong reason: {pruned[0]['reason']}"
    
    log(f"[promotion_smoke] remaining_active_count={len(remaining)}")
    log(f"[promotion_smoke] pruned_count={len(pruned)}")
    log(f"[promotion_smoke] pruned_reason={pruned[0]['reason']}")
    
    log("[promotion_smoke] Test 2 PASSED: Basic pruning works")
    return True

def test_all_prune_conditions():
    """Test 3: All prune conditions (winrate, trades, ROI)."""
    log("[promotion_smoke] Testing all prune conditions...")
    
    from strategy.promotion import (
        daily_prune_and_promote,
        PromotionParams,
        WalletProfileInput,
    )
    from integration.reject_reasons import (
        WALLET_WINRATE_7D_LOW,
        WALLET_TRADES_7D_LOW,
        WALLET_ROI_7D_LOW,
    )
    
    params = PromotionParams(
        prune_winrate_7d_min=0.55,
        prune_trades_7d_min=8,
        prune_roi_7d_min=-0.10,
        promote_winrate_30d_min=0.62,
        promote_roi_30d_min=0.18,
        promote_trades_30d_min=45,
        max_candidates_to_promote=30,
    )
    
    active_wallets = [
        WalletProfileInput(
            wallet="low_winrate",
            winrate_7d=0.40,
            winrate_7d=0.40,
            trades_7d=10,
            roi_7d=0.05,
            winrate_30d=0.55,
            roi_30d=0.10,
            trades_30d=100,
        ),
        WalletProfileInput(
            wallet="low_trades",
            winrate_7d=0.65,
            trades_7d=5,
            roi_7d=0.12,
            winrate_30d=0.70,
            roi_30d=0.25,
            trades_30d=120,
        ),
        WalletProfileInput(
            wallet="low_roi",
            winrate_7d=0.65,
            trades_7d=15,
            roi_7d=-0.25,
            winrate_30d=0.70,
            roi_30d=0.25,
            trades_30d=120,
        ),
        WalletProfileInput(
            wallet="good_wallet",
            winrate_7d=0.70,
            trades_7d=20,
            roi_7d=0.15,
            winrate_30d=0.75,
            roi_30d=0.30,
            trades_30d=150,
        ),
    ]
    
    candidates = []
    
    remaining, pruned = daily_prune_and_promote(active_wallets, candidates, params)
    
    # Should have 1 remaining
    assert len(remaining) == 1, f"Expected 1 remaining, got {len(remaining)}"
    
    # Should have 3 pruned
    assert len(pruned) == 3, f"Expected 3 pruned, got {len(pruned)}"
    
    # Verify each has correct reason
    pruned_reasons = {p["wallet"]: p["reason"] for p in pruned}
    assert pruned_reasons["low_winrate"] == WALLET_WINRATE_7D_LOW
    assert pruned_reasons["low_trades"] == WALLET_TRADES_7D_LOW
    assert pruned_reasons["low_roi"] == WALLET_ROI_7D_LOW
    
    for p in pruned:
        log(f"[promotion_smoke] pruned {p['wallet']}: {p['reason']}")
    
    log("[promotion_smoke] Test 3 PASSED: All prune conditions work")
    return True

def test_promotion():
    """Test 4: Promotion of qualified candidates."""
    log("[promotion_smoke] Testing promotion logic...")
    
    from strategy.promotion import (
        daily_prune_and_promote,
        PromotionParams,
        WalletProfileInput,
    )
    
    params = PromotionParams(
        prune_winrate_7d_min=0.55,
        prune_trades_7d_min=8,
        prune_roi_7d_min=-0.10,
        promote_winrate_30d_min=0.62,
        promote_roi_30d_min=0.18,
        promote_trades_30d_min=45,
        max_candidates_to_promote=30,
    )
    
    active_wallets = [
        WalletProfileInput(
            wallet="good_active",
            winrate_7d=0.65,
            trades_7d=15,
            roi_7d=0.12,
            winrate_30d=0.70,
            roi_30d=0.25,
            trades_30d=120,
        ),
    ]
    
    candidates = [
        WalletProfileInput(
            wallet="qualified_candidate",
            winrate_7d=0.68,
            trades_7d=12,
            roi_7d=0.08,
            winrate_30d=0.72,
            roi_30d=0.25,
            trades_30d=80,
        ),
        WalletProfileInput(
            wallet="unqualified_candidate",
            winrate_7d=0.50,
            trades_7d=8,
            roi_7d=-0.05,
            winrate_30d=0.58,
            roi_30d=0.12,
            trades_30d=40,
        ),
    ]
    
    remaining, pruned = daily_prune_and_promote(active_wallets, candidates, params)
    
    # Should have 2 remaining (1 old + 1 promoted)
    assert len(remaining) == 2, f"Expected 2 remaining, got {len(remaining)}"
    
    # Should have 0 pruned (only unqualified candidate not promoted)
    assert len(pruned) == 0, f"Expected 0 pruned, got {len(pruned)}"
    
    # Verify qualified candidate was promoted
    wallets = [w.wallet for w in remaining]
    assert "qualified_candidate" in wallets, "Qualified candidate should be promoted"
    assert "unqualified_candidate" not in wallets, "Unqualified candidate should not be promoted"
    
    log(f"[promotion_smoke] remaining_after_promotion={wallets}")
    
    log("[promotion_smoke] Test 4 PASSED: Promotion works")
    return True

def main():
    log("[promotion_smoke] Starting PR-H.3 smoke tests...")
    
    tests = [
        test_prune_reasons_known,
        test_basic_pruning,
        test_all_prune_conditions,
        test_promotion,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            log(f"[promotion_smoke] FAILED: {test.__name__}: {e}")
            failed += 1
    
    log(f"[promotion_smoke] Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        log("[promotion_smoke] OK")
        return 0
    else:
        log("[promotion_smoke] FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
PYTHON_IMPORT
