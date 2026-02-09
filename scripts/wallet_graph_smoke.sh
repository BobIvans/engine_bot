#!/bin/bash
# scripts/wallet_graph_smoke.sh

set -e

echo "[overlay_lint] running wallet_graph smoke..."

cd "$(dirname "$0")/.."

# Create temporary output files
OUTPUT_JSONL=$(mktemp)
SUMMARY_JSON=$(mktemp)

cleanup() {
    rm -f "$OUTPUT_JSONL" "$SUMMARY_JSON"
}
trap cleanup EXIT

# Run pipeline on fixture
python3 -m ingestion.pipelines.wallet_cluster_pipeline \
    --input integration/fixtures/discovery/trades_norm_co_trade_sample.jsonl \
    --output "$OUTPUT_JSONL" \
    --dry-run \
    --summary-json 2>/dev/null > "$SUMMARY_JSON"

# Check summary JSON
if [ ! -s "$SUMMARY_JSON" ]; then
    echo "[wallet_graph_smoke] FAILED: No summary JSON output"
    exit 1
fi

# Validate clusters_count is 1 (Wallet11+Wallet22 form one cluster, Wallet33 is isolated)
CLUSTERS_COUNT=$(python3 -c "import sys, json; print(json.load(sys.stdin)['clusters_count'])" < "$SUMMARY_JSON")
if [ -z "$CLUSTERS_COUNT" ]; then
    echo "[wallet_graph_smoke] FAILED: Could not parse clusters_count"
    exit 1
fi

if [ "$CLUSTERS_COUNT" -ne 1 ]; then
    echo "[wallet_graph_smoke] FAILED: Expected clusters_count=1, got $CLUSTERS_COUNT"
    exit 1
fi

# Validate total_wallets is 2 (only Wallet11+Wallet22 are in clusters)
TOTAL_WALLETS=$(python3 -c "import sys, json; print(json.load(sys.stdin)['total_wallets'])" < "$SUMMARY_JSON")
if [ "$TOTAL_WALLETS" -ne 2 ]; then
    echo "[wallet_graph_smoke] FAILED: Expected total_wallets=2, got $TOTAL_WALLETS"
    exit 1
fi

# Additional validation: check that dry-run output contains expected info
echo "[wallet_graph_smoke] built co-trade graph: $TOTAL_WALLETS wallets, $CLUSTERS_COUNT cluster(s)"

python3 -m ingestion.pipelines.wallet_cluster_pipeline \
    --input integration/fixtures/discovery/trades_norm_co_trade_sample.jsonl \
    --output "$OUTPUT_JSONL" \
    --dry-run 2>&1 | grep -q "Wallet111111111111111111111111111111" || echo "[wallet_graph_smoke] WARNING: Expected wallet in dry-run output"

echo "[wallet_graph_smoke] OK"
