#!/bin/bash
# scripts/realtime_smoke.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[realtime_smoke] Starting runner smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

from integration.realtime_runner import RealtimeRunner
from integration.token_snapshot_store import TokenSnapshot
from integration.portfolio_stub import PortfolioStub

# Mock RPC source
class MockRpcSource:
    def __init__(self):
        self.trade_sequence = [
            # Iteration 1
            [
                {"ts": "1700000000", "wallet": "Wallet1", "mint": "GoodToken123", "side": "BUY", "price": 0.001, "size_usd": 100.0, "tx_hash": "Sig001", "platform": "raydium"},
                {"ts": "1700000001", "wallet": "Wallet2", "mint": "BadToken456", "side": "BUY", "price": 0.001, "size_usd": 50.0, "tx_hash": "Sig002", "platform": "raydium"},
            ],
            # Iteration 2
            [
                {"ts": "1700000002", "wallet": "Wallet1", "mint": "GoodToken789", "side": "BUY", "price": 0.002, "size_usd": 150.0, "tx_hash": "Sig003", "platform": "jupiter"},
            ],
        ]
        self.call_count = 0
    
    def poll_new_records(self, wallet, stop_at_signature=None, limit=50):
        if self.call_count >= len(self.trade_sequence):
            return []
        trades = self.trade_sequence[self.call_count]
        self.call_count += 1
        return trades

# Create mock snapshot store
class MockSnapshotStore:
    def get(self, mint):
        return TokenSnapshot(
            mint=mint,
            liquidity_usd=50000.0,
            volume_24h_usd=100000.0,
            spread_bps=10.0,
            extra={"security": {"is_honeypot": False, "freeze_authority": None, "mint_authority": None}}
        )

# Test config
config = {
    "version": "1.0.0",
    "strategy_name": "realtime_smoke_test",
    "tracked_wallets": ["Wallet1"],
    "min_edge_bps": 0,  # Set to 0 to allow edge calculation
    "risk": {
        "limits": {
            "max_open_positions": 5,
            "cooldown_sec": 0,
        }
    },
    "honeypot": {
        "enabled": True,
        "reject_if_honeypot": True,
        "reject_if_freeze_authority": True,
        "reject_if_mint_authority": True,
    },
    "token_profile": {
        "min_liquidity_usd": 10000,
        "min_volume_24h_usd": 10000,
        "max_spread_bps": 50,
    },
}

# Create runner with mocked dependencies
runner = RealtimeRunner(
    config=config,
    source=MockRpcSource(),
    snapshot_store=MockSnapshotStore(),
    portfolio=PortfolioStub(equity_usd=10000.0, peak_equity_usd=10000.0),
    interval_sec=1,
)

print("[realtime_smoke] Starting runner for 2 iterations...", file=sys.stderr)

# Run for max 2 iterations
runner.run_loop(max_iterations=2)

# Verify results
trades_processed = len([w for w in runner.last_signatures.values() if w])
print(f"[realtime_smoke] Processed iterations: 2", file=sys.stderr)
print(f"[realtime_smoke] Last signatures: {runner.last_signatures}", file=sys.stderr)
print(f"[realtime_smoke] Portfolio equity: {runner.portfolio.equity_usd}", file=sys.stderr)
print(f"[realtime_smoke] Open positions: {runner.portfolio.open_positions}", file=sys.stderr)

# Verify the loop ran correctly
if trades_processed >= 1:
    print("[realtime_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
else:
    print("[realtime_smoke] FAIL: Expected trades to be processed", file=sys.stderr)
    sys.exit(1)
PYTHON_TEST

echo "[realtime_smoke] Smoke test completed." >&2
