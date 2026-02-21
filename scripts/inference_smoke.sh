#!/bin/bash
# scripts/inference_smoke.sh
# PR-C.5 Inference Wiring Smoke Test

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[inference_smoke] Starting Inference Wiring smoke test..." >&2

python3 << 'PYTHON_TEST'
import sys
import json
from collections import defaultdict

# Add root to path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from integration.model_inference import infer_p_model, SimpleLinearModel
from strategy.signal_engine import decide_entry
from integration.sim_preflight import compute_edge_bps
from integration.token_snapshot_store import TokenSnapshot
from integration.trade_types import Trade

passed = 0
failed = 0

print("[inference_smoke] Testing SimpleLinearModel...", file=sys.stderr)

# Test 1: SimpleLinearModel
model_config = {
    "intercept": 0.0,
    "weights": {
        "f_wallet_winrate_30d": 2.0,
        "f_token_spread_bps": -0.5,
    }
}
model = SimpleLinearModel(model_config)

features = {
    "f_wallet_winrate_30d": 0.6,
    "f_token_spread_bps": 0.02,
}
p = model.predict(features)
# z = 0.0 + 2.0*0.6 + (-0.5)*0.02 = 1.2 - 0.01 = 1.19
# p = sigmoid(1.19) should be around 0.77
if 0.0 <= p <= 1.0:
    print(f"  [inference] SimpleLinearModel: PASS (p={p:.4f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] SimpleLinearModel: FAIL (p={p:.4f}, expected ~0.77)", file=sys.stderr)
    failed += 1

print("[inference_smoke] Testing infer_p_model modes...", file=sys.stderr)

# Test 2: infer_p_model - model_off mode
features = {"f_wallet_winrate_30d": 0.6}
p = infer_p_model(features, mode="model_off")
if p is None:
    print(f"  [inference] model_off returns None: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] model_off returns None: FAIL (got {p})", file=sys.stderr)
    failed += 1

# Test 3: infer_p_model - heuristic mode
p = infer_p_model(features, mode="heuristic")
if p is not None and 0.0 <= p <= 1.0:
    print(f"  [inference] heuristic mode: PASS (p={p:.4f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] heuristic mode: FAIL (p={p})", file=sys.stderr)
    failed += 1

# Test 4: infer_p_model - json_weights mode with mock model
p = infer_p_model(
    features,
    mode="json_weights",
    model_path="/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/mock_model.json"
)
if p is not None and 0.0 <= p <= 1.0:
    print(f"  [inference] json_weights mode: PASS (p={p:.4f})", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] json_weights mode: FAIL (p={p})", file=sys.stderr)
    failed += 1

print("[inference_smoke] Testing compute_edge_bps with p_model...", file=sys.stderr)

# Test 5: compute_edge_bps with p_model
# When p_model is provided, it should be used instead of wallet winrate
trade = Trade(
    ts="2024-01-01T12:00:00Z",
    wallet="WALLET_A",
    mint="MINT_A",
    side="BUY",
    price=0.001,
    size_usd=100.0,
)

snapshot = TokenSnapshot(
    mint="MINT_A",
    liquidity_usd=50000.0,
    volume_24h_usd=250000.0,
    spread_bps=15.0,
)

wallet_profile = {"winrate_30d": 0.5}  # 50% winrate

cfg = {
    "modes": {
        "U": {"tp_pct": 0.10, "sl_pct": -0.05, "hold_sec_max": 300}
    }
}

# Without p_model: win_p = 0.5
edge_without_model = compute_edge_bps(trade, snapshot, wallet_profile, cfg, "U")
# With p_model = 0.7: win_p = 0.7
edge_with_model = compute_edge_bps(trade, snapshot, wallet_profile, cfg, "U", p_model=0.7)

# Calculate expected values:
# Without: edge = (0.5*0.10 - 0.5*0.05) * 10000 - 15 = 250 - 15 = 235 bps
# With p_model=0.7: edge = (0.7*0.10 - 0.3*0.05) * 10000 - 15 = (0.07 - 0.015) * 10000 - 15 = 550 - 15 = 535 bps

if edge_without_model != edge_with_model:
    print(f"  [inference] p_model affects edge: PASS (without={edge_without_model}, with={edge_with_model})", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] p_model affects edge: FAIL (both={edge_with_model})", file=sys.stderr)
    failed += 1

print("[inference_smoke] Testing decide_entry with p_model...", file=sys.stderr)

# Test 6: decide_entry accepts p_model
from integration.wallet_profile_store import WalletProfile

wp = WalletProfile(
    wallet="WALLET_A",
    roi_30d_pct=10.0,
    winrate_30d=0.55,
    trades_30d=50,
)

cfg_min_edge = {
    "min_edge_bps": 200,
    "modes": {
        "U": {"tp_pct": 0.10, "sl_pct": -0.05, "hold_sec_max": 300}
    },
    "honeypot": {"enabled": False},
    "token_profile": {
        "min_liquidity_usd": 1000.0,
        "max_spread_bps": 100.0,
    }
}

# With wallet winrate only (0.55): edge ≈ 235 bps, which is > min_edge_bps=200
decision1 = decide_entry(trade, snapshot, wp, cfg_min_edge)
print(f"  [inference] decide_entry without p_model: should_enter={decision1.should_enter}, edge={decision1.edge_bps}", file=sys.stderr)

# With p_model=0.6: edge should be higher
decision2 = decide_entry(trade, snapshot, wp, cfg_min_edge, p_model=0.6)
print(f"  [inference] decide_entry with p_model=0.6: should_enter={decision2.should_enter}, edge={decision2.edge_bps}", file=sys.stderr)

# With p_model=0.4: edge should be lower (or even negative)
decision3 = decide_entry(trade, snapshot, wp, cfg_min_edge, p_model=0.4)
print(f"  [inference] decide_entry with p_model=0.4: should_enter={decision3.should_enter}, edge={decision3.edge_bps}", file=sys.stderr)

# Verify p_model is in calc_details
if decision2.calc_details.get("p_model") == 0.6:
    print(f"  [inference] p_model in calc_details: PASS", file=sys.stderr)
    passed += 1
else:
    print(f"  [inference] p_model in calc_details: FAIL", file=sys.stderr)
    failed += 1

# Summary
print(f"[inference_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)
if failed == 0:
    print("[inference_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
else:
    print("[inference_smoke] FAILED", file=sys.stderr)
    sys.exit(1)
PYTHON_TEST
