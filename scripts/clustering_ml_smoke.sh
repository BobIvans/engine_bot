#!/bin/bash
# scripts/clustering_ml_smoke.sh
# Smoke test for Wallet Clustering ML Pipeline
# PR-V.1

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[clustering_smoke]${NC} $1"
}

log_error() {
    echo -e "${RED}[clustering_smoke] ERROR:${NC} $1" >&2
    exit 1
}

# Add project root to PYTHONPATH
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

echo ""
log_info "Starting Wallet Clustering smoke tests..."
echo ""

# Skip gracefully in minimal environments where optional ML deps are absent.
if ! python3 -c "import pandas" >/dev/null 2>&1; then
    echo "[clustering_smoke] WARNING: pandas not installed; skipping ML clustering smoke in minimal environment" >&2
    echo "[clustering_smoke] OK (skipped: missing optional dependency pandas)" >&2
    exit 0
fi

python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')

import pandas as pd
import json

from strategy.analytics.wallet_features import extract_features
from strategy.analytics.clustering import WalletClusterer

print("[clustering_smoke] Testing feature extraction...")
print("")

# Load synthetic trades fixture
fixture_path = "integration/fixtures/clustering/synthetic_trades.jsonl"
trades = []
with open(fixture_path, 'r') as f:
    for line in f:
        if line.strip():
            trades.append(json.loads(line))

trades_df = pd.DataFrame(trades)
print(f"  Loaded {len(trades)} trades for {trades_df['wallet'].nunique()} wallets")
print(f"  Trade columns: {list(trades_df.columns)}")
print("")

# Extract features
features_df = extract_features(trades_df)
print(f"  Features extracted: {features_df.shape} (OK)")
print("")

# Check that we have features for all wallets
expected_wallets = trades_df['wallet'].unique()
actual_wallets = features_df.index.tolist()
print(f"  Wallets in features: {len(actual_wallets)} (expected {len(expected_wallets)})")

# Verify all expected wallets are present
for w in expected_wallets:
    assert w in actual_wallets, f"Wallet {w} not in features"
print("  All wallets present in features (OK)")
print("")

# Test clustering
print("[clustering_smoke] Testing K-Means clustering...")
clusterer = WalletClusterer(n_clusters=4, random_state=42)
labels = clusterer.fit_predict(trades_df)

print(f"  Clusters found: {dict(labels.value_counts())}")

# Get cluster stats
stats = clusterer.get_cluster_stats(trades_df)
print(f"  Cluster statistics: {stats}")
print("")

# Test determinism - run twice and check results are identical
print("[clustering_smoke] Testing determinism (random_state=42)...")
clusterer2 = WalletClusterer(n_clusters=4, random_state=42)
labels2 = clusterer2.fit_predict(trades_df)

assert labels.equals(labels2), "Results should be identical with same random_state"
print("  Determinism verified (OK)")
print("")

# Check that snipers have lower entry delay than noise
print("[clustering_smoke] Testing semantic label assignment...")

# Find Sniper and Noise clusters
sniper_labels = [l for l in stats.keys() if 'Sniper' in l or 'Leader' in l]
noise_labels = [l for l in stats.keys() if 'Noise' in l or 'Loser' in l or 'Follower' in l]

print(f"  Sniper-like labels: {sniper_labels}")
print(f"  Non-sniper labels: {noise_labels}")

if sniper_labels and noise_labels:
    # Get average delay for sniper and noise clusters
    sniper_delay = stats[sniper_labels[0]]['avg_delay']
    noise_delay = stats[noise_labels[0]]['avg_delay']
    
    print(f"  Sniper avg delay: {sniper_delay:.1f}s")
    print(f"  Noise avg delay: {noise_delay:.1f}s")
    
    # Snipers should have lower delay than noise/losers
    if 'Noise' in noise_labels[0] or 'Loser' in noise_labels[0]:
        assert sniper_delay < noise_delay, f"Sniper delay ({sniper_delay}) should be < Noise delay ({noise_delay})"
        print(f"  Centroid check: Sniper delay < Noise delay (OK)")
    else:
        print(f"  Centroid check: Skipped (no Noise cluster found)")
else:
    print(f"  WARNING: Could not find expected cluster labels")
    print(f"  Available labels: {list(stats.keys())}")

print("")

# Verify that fit is reproducible
print("[clustering_smoke] Testing reproducibility...")
centroids1 = clusterer.get_centroids()
clusterer3 = WalletClusterer(n_clusters=4, random_state=42)
clusterer3.fit(trades_df)
centroids2 = clusterer3.get_centroids()

# Centroids should be very close (within floating point tolerance)
diff = (centroids1 - centroids2).abs().max().max()
assert diff < 1e-10, f"Centroids should be identical, max diff: {diff}"
print(f"  Reproducibility verified: max centroid diff = {diff:.2e} (OK)")
print("")

print("[clustering_smoke] All clustering tests passed!")
print("[clustering_smoke] OK")
PYTEST
