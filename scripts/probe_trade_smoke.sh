#!/bin/bash
#
# scripts/probe_trade_smoke.sh
#
# Deterministic smoke test for Probe Trade Logic (PR-K.2).
# Tests evaluate_probe and integration with signal_engine.
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../"

echo "[overlay_lint] running probe trade smoke..." >&2

# Run the smoke test using Python
python3 - << 'PYTHON_TEST'
import sys
from dataclasses import asdict

# Import the modules
from strategy.probing import evaluate_probe, evaluate_probe_from_dict, ProbeResult
from strategy.signal_engine import decide_entry
from integration.trade_types import Trade
from integration.token_snapshot_store import TokenSnapshot

# Test configurations
cfg_disabled = {
    "token_profile": {
        "honeypot": {
            "probe_trade": {
                "enabled": False,
                "max_probe_cost_usd": 10.0,
            }
        }
    }
}

cfg_enabled = {
    "token_profile": {
        "honeypot": {
            "probe_trade": {
                "enabled": True,
                "max_probe_cost_usd": 10.0,
            }
        }
    }
}

errors = []

# Test 1: Config disabled -> is_probe=False
print("Test 1: Config disabled", file=sys.stderr)
result = evaluate_probe_from_dict(None, 100.0, cfg_disabled)
if result.is_probe:
    errors.append("Test 1 FAILED: Expected is_probe=False when disabled")
else:
    print("  PASS", file=sys.stderr)

# Test 2: Config enabled, no snapshot data -> is_probe=True, size capped
print("Test 2: No snapshot data", file=sys.stderr)
result = evaluate_probe_from_dict(None, 100.0, cfg_enabled)
if not result.is_probe:
    errors.append("Test 2 FAILED: Expected is_probe=True when no data")
elif result.size_usd != 10.0:
    errors.append(f"Test 2 FAILED: Expected size=10.0, got {result.size_usd}")
else:
    print("  PASS", file=sys.stderr)

# Test 3: Config enabled, probe_passed=True -> is_probe=False
print("Test 3: Probe already passed", file=sys.stderr)
probe_state = {"passed": True}
result = evaluate_probe_from_dict(probe_state, 100.0, cfg_enabled)
if result.is_probe:
    errors.append("Test 3 FAILED: Expected is_probe=False when probe passed")
else:
    print("  PASS", file=sys.stderr)

# Test 4: Config enabled, probe_passed=False -> is_probe=True
print("Test 4: Probe not passed", file=sys.stderr)
probe_state = {"passed": False}
result = evaluate_probe_from_dict(probe_state, 100.0, cfg_enabled)
if not result.is_probe:
    errors.append("Test 4 FAILED: Expected is_probe=True when probe not passed")
elif result.size_usd != 10.0:
    errors.append(f"Test 4 FAILED: Expected size=10.0, got {result.size_usd}")
else:
    print("  PASS", file=sys.stderr)

# Test 5: Config enabled, small trade size -> no capping needed
print("Test 5: Small trade size", file=sys.stderr)
probe_state = {"passed": False}
result = evaluate_probe_from_dict(probe_state, 5.0, cfg_enabled)
if not result.is_probe:
    errors.append("Test 5 FAILED: Expected is_probe=True when probe not passed")
elif result.size_usd != 5.0:
    errors.append(f"Test 5 FAILED: Expected size=5.0 (no capping), got {result.size_usd}")
else:
    print("  PASS", file=sys.stderr)

# Test 6: Integration with decide_entry
print("Test 6: Integration with decide_entry", file=sys.stderr)

# Create a mock trade
trade = Trade(
    ts="1700000000",
    wallet="TestWallet111111111111111111111111",
    mint="TestMint111111111111111111111111111",
    side="BUY",
    price=1.0,
    size_usd=100.0,
    platform="jupiter",
    tx_hash="TestTx111111111111111111111111111"
)

# Create snapshot with probe_passed=True
snap_passed = TokenSnapshot(
    mint=trade.mint,
    ts_snapshot=1700000000,
    liquidity_usd=50000,
    volume_24h_usd=100000,
    spread_bps=50,
    top10_holders_pct=25.0,
    single_holder_pct=10.0,
    extra={"probe_state": {"passed": True}}
)

# Create snapshot with probe_passed=False
snap_not_passed = TokenSnapshot(
    mint=trade.mint,
    ts_snapshot=1700000000,
    liquidity_usd=50000,
    volume_24h_usd=100000,
    spread_bps=50,
    top10_holders_pct=25.0,
    single_holder_pct=10.0,
    extra={"probe_state": {"passed": False}}
)

# Test 6a: Probe passed -> is_probe=False
cfg_minimal = {
    "min_edge_bps": 0,
    "token_profile": {
        "honeypot": {
            "enabled": False,  # Disable other checks
            "probe_trade": {
                "enabled": True,
                "max_probe_cost_usd": 10.0,
            }
        }
    }
}

decision = decide_entry(trade, snap_passed, None, cfg_minimal)
if not decision.should_enter:
    errors.append("Test 6a FAILED: Expected should_enter=True")
elif decision.calc_details.get("probe", {}).get("is_probe"):
    errors.append("Test 6a FAILED: Expected is_probe=False when probe passed")
else:
    print("  6a PASS", file=sys.stderr)

# Test 6b: Probe not passed -> is_probe=True, size capped
decision = decide_entry(trade, snap_not_passed, None, cfg_minimal)
if not decision.should_enter:
    errors.append("Test 6b FAILED: Expected should_enter=True")
elif not decision.calc_details.get("probe", {}).get("is_probe"):
    errors.append("Test 6b FAILED: Expected is_probe=True in calc_details")
elif decision.calc_details.get("probe", {}).get("suggested_size_usd") != 10.0:
    errors.append("Test 6b FAILED: Expected suggested_size_usd=10.0 in calc_details")
else:
    print("  6b PASS", file=sys.stderr)

# Test 7: Verify ProbeResult is a frozen dataclass
print("Test 7: ProbeResult immutability", file=sys.stderr)
result = evaluate_probe_from_dict(None, 100.0, cfg_enabled)
try:
    result.is_probe = False
    errors.append("Test 7 FAILED: ProbeResult should be frozen/immutable")
except Exception:
    print("  PASS", file=sys.stderr)

# Test 8: Check default max_probe_cost_usd
print("Test 8: Default max_probe_cost_usd", file=sys.stderr)
cfg_no_max = {
    "token_profile": {
        "honeypot": {
            "probe_trade": {
                "enabled": True,
                # No max_probe_cost_usd specified
            }
        }
    }
}
result = evaluate_probe_from_dict(None, 100.0, cfg_no_max)
if result.size_usd != 10.0:  # Default is 10.0
    errors.append(f"Test 8 FAILED: Expected default size=10.0, got {result.size_usd}")
else:
    print("  PASS", file=sys.stderr)

# Print errors and exit
if errors:
    print("\\nERRORS found:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)

print("\\n[probe_trade_smoke] OK ✅", file=sys.stderr)
PYTHON_TEST

exit_code=$?
exit $exit_code
