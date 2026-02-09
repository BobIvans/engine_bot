#!/bin/bash
# scripts/config_hot_reload_smoke.sh
# Smoke test for Config Hot-Reload (PR-Y.5)

set -e

# Setup
mkdir -p /tmp/hot_reload_test
CONFIG_FILE="/tmp/hot_reload_test/test_config.yaml"
TRADES_FILE="/tmp/hot_reload_test/trades.jsonl" 

echo "Generating 5000 dummy trades..."
python3 -c 'import json; print("\n".join([json.dumps({"ts": "2025-01-01T00:00:00.000Z", "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "amount": 100, "price": 1.0, "side": "BUY", "wallet": "w1", "lineno": i}) for i in range(5000)]))' > "$TRADES_FILE"

# Copy base config
cp integration/fixtures/config/base.yaml "$CONFIG_FILE"

# Add required structure for config_loader validation (it expects full params_base structure)
# config_loader checks: version, strategy_name, run.mode, subtrees
# We need to wrap the flat runtime fields into the full structure?
# Wait, integration/fixtures/config/base.yaml is FLAT.
# ConfigReloader reads FLAT runtime schema.
# BUT config_loader.load_params_base reads FULL params_base.yaml.
# If I pass `base.yaml` to `--config`, load_params_base will FAIL because it expects nested structure.
# I need to create a FULL config file that incorporates the runtime fields.

echo "Creating valid full config..."
cat <<EOF > "$CONFIG_FILE"
version: "3.0"
strategy_name: "hot-reload-test"
run:
  mode: "paper"
  safety:
    live_trading_enabled: false

signals:
  edge_threshold_base: 0.05
  min_edge_bps: 500

risk:
  position_pct: 0.02
  sizing:
    method: "fixed_pct"
    fixed_pct_of_bankroll: 2.0
  limits:
    max_open_positions: 3
    max_exposure_per_token_pct: 0.10
    max_daily_loss_pct: 0.05
    cooldown:
      duration_sec: 300
    tier_limits: {}

wallet_profile: {}
token_profile: {}
execution: {}
EOF

# Start pipeline in background
echo "[test] Starting pipeline with --hot-reload-config..."
# Run as module to fix imports
# Slow down to ensuring it runs for at least 5s (5000 * 0.001 = 5s)
export PAPER_PIPELINE_SLEEP_SEC=0.001
python3 -m integration.paper_pipeline \
    --config "$CONFIG_FILE" \
    --trades-jsonl "$TRADES_FILE" \
    --hot-reload-config \
    --dry-run \
    --summary-json > /tmp/hot_reload_test/output.log 2> /tmp/hot_reload_test/stderr.log &

PID=$!
echo "[test] Pipeline PID: $PID"

# Wait for startup
sleep 3

# Check if running
if ! kill -0 $PID 2>/dev/null; then
    echo "[fail] Pipeline exited prematurely"
    cat /tmp/hot_reload_test/stderr.log
    exit 1
fi

echo "[test] Verify initial load..."
if grep -q "Started watching" /tmp/hot_reload_test/stderr.log; then
    echo "[ok] Watcher started"
else
    echo "[fail] Watcher NOT started"
    kill $PID
    exit 1
fi


# 1. Modify config (VALID)
echo "[test] Modifying config (Valid Update)..."
# Update edge_threshold_base and position_pct
# We use sed to replace values in the file.
sed -i '' 's/edge_threshold_base: 0.05/edge_threshold_base: 0.04/' "$CONFIG_FILE"
# Wait for reload
sleep 2

if grep -q "Detected change" /tmp/hot_reload_test/stderr.log; then
    echo "[ok] Change detected"
else
    echo "[fail] Change NOT detected"
    cat /tmp/hot_reload_test/stderr.log
    kill $PID
    exit 1
fi

if grep -q "Reloaded:" /tmp/hot_reload_test/stderr.log; then
    echo "[ok] Reload successful"
else
    echo "[fail] Reload log missing"
    cat /tmp/hot_reload_test/stderr.log
    kill $PID
    exit 1
fi

# 2. Modify config (INVALID)
echo "[test] Modifying config (Invalid Update)..."
# Set invalid value (e.g. edge_threshold_base > 1.0)
sed -i '' 's/edge_threshold_base: 0.04/edge_threshold_base: 2.5/' "$CONFIG_FILE"
sleep 2

if grep -q "Reload FAILED" /tmp/hot_reload_test/stderr.log; then
    echo "[ok] Invalid config rejected (Reload FAILED logged)"
else
    echo "[fail] Invalid config NOT rejected"
    cat /tmp/hot_reload_test/stderr.log
    kill $PID
    exit 1
fi

# Cleanup
echo "[ok] Smoke test passed."
kill $PID
rm -rf /tmp/hot_reload_test
exit 0

EOF
