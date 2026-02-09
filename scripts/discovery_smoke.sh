#!/bin/bash
# scripts/discovery_smoke.sh
# PR-H.1 Wallet Discovery Pipeline - Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${SCRIPT_DIR}")" && pwd)"

echo "[discovery_smoke] Starting wallet discovery smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import json
import tempfile
import os

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [discovery] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [discovery] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[discovery_smoke] Testing WalletDiscoverySummary...", file=sys.stderr)

from integration.wallet_discovery import WalletDiscoverySummary

# Test 1: Summary dataclass
summary = WalletDiscoverySummary()
test_case("summary_created", summary.total_wallets == 0)
test_case("summary_empty", len(summary.candidates) == 0)

# Test 2: Summary to_dict
summary.total_wallets = 10
summary.accepted = 5
summary_dict = summary.to_dict()
test_case("summary_to_dict_total", summary_dict["total_wallets"] == 10)
test_case("summary_to_dict_accepted", summary_dict["accepted"] == 5)

print("[discovery_smoke] Testing config filter loading...", file=sys.stderr)

from integration.wallet_discovery import load_config_filters

filters = load_config_filters("$ROOT_DIR/strategy/config/params_base.yaml")
test_case("filters_loaded", len(filters) > 0)
test_case("min_roi_30d_pct", filters.get("min_roi_30d_pct") == 20.0)
test_case("min_winrate_30d", filters.get("min_winrate_30d") == 0.60)
test_case("min_trades_30d", filters.get("min_trades_30d") == 50)

print("[discovery_smoke] Testing wallet filtering...", file=sys.stderr)

from integration.wallet_discovery import normalize_wallet_record, filter_wallet

# Test 3: Normalize record
record = {
    "wallet": "test_wallet",
    "roi_30d_pct": "25.0",
    "winrate_30d": "0.70",
    "trades_30d": "100",
}
normalized = normalize_wallet_record(record)
test_case("normalize_wallet", normalized.get("wallet") == "test_wallet")
test_case("normalize_roi", normalized.get("roi_30d") == 25.0)
test_case("normalize_winrate", normalized.get("winrate") == 0.70)
test_case("normalize_trades", normalized.get("trades_30d") == 100)

# Test 4: Filter wallet - should pass
filters = {
    "min_roi_30d_pct": 20.0,
    "min_winrate_30d": 0.60,
    "min_trades_30d": 50,
    "min_avg_trade_size_sol": 0.20,
    "min_wallet_age_days": 7,
}
wallet = {
    "wallet": "7nYAh1wXYZ4sL5YmR8XZ1yZW2Xg6iZw4z3Xp3KZwPNp1",
    "roi_30d": 45.5,
    "winrate": 0.78,
    "trades_30d": 120,
    "avg_trade_size": 0.85,
    "wallet_age": 45,
}
passed, reason = filter_wallet(wallet, filters)
test_case("wallet_passes_filters", passed == True)

# Test 5: Filter wallet - should fail (low ROI)
wallet_low_roi = {
    "wallet": "8pZBHm5c2k9m0n3p4r5s8t0v9w2x4y6z1a3b5c7d",
    "roi_30d": 15.2,
    "winrate": 0.65,
    "trades_30d": 80,
}
passed, reason = filter_wallet(wallet_low_roi, filters)
test_case("wallet_fails_low_roi", passed == False)
test_case("roi_failure_reason", "ROI" in reason)

# Test 6: Filter wallet - should fail (low trades)
wallet_low_trades = {
    "wallet": "9qACIn6d3l0o1n4q5s9t1u0w3x5y7z2b4d6f8",
    "roi_30d": 55.8,
    "winrate": 0.82,
    "trades_30d": 30,
}
passed, reason = filter_wallet(wallet_low_trades, filters)
test_case("wallet_fails_low_trades", passed == False)
test_case("trades_failure_reason", "Trades" in reason)

print("[discovery_smoke] Testing full pipeline...", file=sys.stderr)

from integration.wallet_discovery import discover_wallets

# Create temp input file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    f.write("""wallet,roi_30d_pct,winrate_30d,trades_30d,avg_trade_size_sol,wallet_age_days
7nYAh1wXYZ4sL5YmR8XZ1yZW2Xg6iZw4z3Xp3KZwPNp1,45.5,0.78,120,0.85,45
8pZBHm5c2k9m0n3p4r5s8t0v9w2x4y6z1a3b5c7d9e,15.2,0.65,80,0.45,12
9qACIn6d3l0o1n4q5s9t1u0w3x5y7z2b4d6f8h0j2l,55.8,0.82,200,1.20,90
""")
    input_file = f.name

try:
    with open(input_file) as f:
        summary = discover_wallets(
            input_file=f,
            config_path="$ROOT_DIR/strategy/config/params_base.yaml",
        )

    test_case("pipeline_total_3", summary.total_wallets == 3)
    test_case("pipeline_accepted_2", summary.accepted == 2)  # Wallet 1 and 3 should pass
    test_case("pipeline_rejected_1", summary.filtered_by_roi == 1)  # Wallet 2 should fail (low ROI)
    test_case("pipeline_has_candidates", len(summary.candidates) == 2)

    # Verify candidates
    candidate_wallets = [c["wallet"] for c in summary.candidates]
    test_case("first_candidate_included", "7nYAh1wXYZ4sL5YmR8XZ1yZW2Xg6iZw4z3Xp3KZwPNp1" in candidate_wallets)
    test_case("second_candidate_included", "9qACIn6d3l0o1n4q5s9t1u0w3x5y7z2b4d6f8h0j2l" in candidate_wallets)

finally:
    os.unlink(input_file)

# Test 7: Verify reject constants exist
from integration.reject_reasons import DUPLICATE_EXECUTION, TX_DROPPED, TX_REORGED
test_case("reject_duplicate_exists", DUPLICATE_EXECUTION == "duplicate_execution")
test_case("reject_dropped_exists", TX_DROPPED == "tx_dropped")
test_case("reject_reorged_exists", TX_REORGED == "tx_reorged")

# Summary
print(f"\n[discovery_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[discovery_smoke] OK", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[discovery_smoke] Smoke test completed." >&2
