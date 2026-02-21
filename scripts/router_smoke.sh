#!/bin/bash
# scripts/router_smoke.sh
# Smoke test for Multi-DEX Router Simulator
# PR-U.4

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[router_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[router_smoke] ERROR:${NC} $1" >&2
    exit 1
}

# Add project root to PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

echo ""
log_info "Starting Multi-DEX Router smoke tests..."
echo ""

python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

from execution.routing.interfaces import LiquiditySource
from execution.routing.types import SimulatedQuote, RouteCandidate
from execution.routing.router import LiquidityRouter

# ============================================
# Mock Liquidity Sources
# ============================================

class MockRaydium(LiquiditySource):
    """Mock Raydium v4 source returning 100.0"""
    _is_local_calc = True
    
    def get_name(self):
        return "raydium_v4"
    
    def get_quote(self, mint_in, mint_out, amount_in):
        # Simulate 100.0 output for 1.0 input
        amount_out = int(amount_in * 100.0)
        return SimulatedQuote(
            mint_in=mint_in,
            mint_out=mint_out,
            amount_in=amount_in,
            amount_out=amount_out,
            price_impact_bps=5,
            fee_atomic=int(amount_in * 0.0025),
        )


class MockOrca(LiquiditySource):
    """Mock Orca source returning 101.0 (best)"""
    _is_local_calc = True
    
    def get_name(self):
        return "orca_whirlpool"
    
    def get_quote(self, mint_in, mint_out, amount_in):
        # Simulate 101.0 output for 1.0 input (best rate)
        amount_out = int(amount_in * 101.0)
        return SimulatedQuote(
            mint_in=mint_in,
            mint_out=mint_out,
            amount_in=amount_in,
            amount_out=amount_out,
            price_impact_bps=3,
            fee_atomic=int(amount_in * 0.002),
        )


class MockJupiter(LiquiditySource):
    """Mock Jupiter API source returning 99.0"""
    _is_local_calc = False
    
    def get_name(self):
        return "jupiter_api"
    
    def get_quote(self, mint_in, mint_out, amount_in):
        # Simulate 99.0 output for 1.0 input
        amount_out = int(amount_in * 99.0)
        return SimulatedQuote(
            mint_in=mint_in,
            mint_out=mint_out,
            amount_in=amount_in,
            amount_out=amount_out,
            price_impact_bps=8,
            fee_atomic=int(amount_in * 0.001),
        )


# ============================================
# Tests
# ============================================

print("[router_smoke] Testing imports...")
print("  All modules imported successfully")
print("  Imports: OK")
print("")

print("[router_smoke] Creating mock liquidity sources...")
print("  MockRaydium: raydium_v4 -> 100.0")
print("  MockOrca: orca_whirlpool -> 101.0 (best)")
print("  MockJupiter: jupiter_api -> 99.0")
print("")

# Initialize router
router = LiquidityRouter()

# Register sources
router.register_source(MockRaydium())
router.register_source(MockOrca())
router.register_source(MockJupiter())

registered = router.get_registered_sources()
assert len(registered) == 3, f"Expected 3 sources, got {len(registered)}"
print(f"  Registered 3 sources. (OK)")
print("")

# Test parameters (SOL to USDC)
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
amount_in = 1000000000  # 1 SOL in lamports

# Get all quotes
all_quotes = router.get_all_quotes(SOL, USDC, amount_in)
assert len(all_quotes) == 3, f"Expected 3 quotes, got {len(all_quotes)}"
print(f"  All quotes count: {len(all_quotes)} (OK)")
print("")

# Find best route (should be Orca with 101.0)
best = router.find_best_route(SOL, USDC, amount_in)
assert best is not None, "Best route should not be None"
expected_amount = int(amount_in * 101.0)
assert best.source_name == "orca_whirlpool", f"Expected orca_whirlpool, got {best.source_name}"
assert best.amount_out == expected_amount, f"Expected {expected_amount}, got {best.amount_out}"
print(f"  Best route found: {best.source_name} -> {best.amount_out} (OK)")
print("")

# Verify price_impact is propagated
assert best.quote.price_impact_bps == 3, f"Expected price_impact_bps=3, got {best.quote.price_impact_bps}"
print(f"  Price impact propagated: {best.quote.price_impact_bps} bps (OK)")
print("")

# Compare routes
comparison = router.compare_routes(SOL, USDC, amount_in)
print(f"  Comparison: {comparison} (OK)")
print("")

# Test empty sources
empty_router = LiquidityRouter()
empty_best = empty_router.find_best_route(SOL, USDC, amount_in)
assert empty_best is None, "Empty router should return None"
print(f"  Empty router handling: None returned (OK)")
print("")

print("  All router tests: PASSED")
print("")
print("[router_smoke] All smoke tests passed!")
print("[router_smoke] OK")
PYTEST
