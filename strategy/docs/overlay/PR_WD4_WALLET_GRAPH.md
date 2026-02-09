# PR-WD.4 — Wallet Graph Builder (Co-Trade Clustering)

**Status:** In Progress  
**Owner:** Strategy Team  
**Created:** 2024-02-08

## Overview

This PR implements an offline pipeline for building co-trade graphs and clustering wallets based on "who follows whom" patterns. The algorithm identifies wallets that consistently trade together and computes leadership metrics.

## Goals

1. Build co-trade adjacency matrix from normalized trades
2. Cluster wallets based on co-trade frequency
3. Compute leader/follower metrics within clusters
4. Enrich wallet profiles with clustering results

## Algorithm

### Co-Trade Detection

```
Δt = |ts_A - ts_B|
If Δt ≤ 60,000ms and both are large buys (size_usd ≥ 2000):
    → Increment co-trade count for (wallet_A, wallet_B)
```

### Clustering

- Threshold-based algorithm (no external dependencies)
- If co_trade_count ≥ 3 → create edge in graph
- Find connected components via BFS

### Leadership Metrics

- **Leader**: First wallet to enter a token in the cluster
- **leader_score**: Normalized frequency of being first (0.0 to 1.0)
- **follower_lag_ms**: Median time lag from leader

## Architecture

```
trades_norm.parquet
        ↓
ingestion/pipelines/wallet_cluster_pipeline.py
        ↓
analysis/wallet_graph.py (pure functions)
        ↓
co_trade_matrix → detect_clusters → compute_leader_metrics
        ↓
wallets_clustered.parquet
```

## Components

### 1. Core Graph Logic (`analysis/wallet_graph.py`)

```python
# Pure functions for clustering
def build_co_trade_matrix(trades, window_ms=60000) -> Dict[Tuple[str,str], int]
def detect_clusters(co_trade_matrix, min_co_trades=3) -> Dict[str, int]
def compute_leader_metrics(trades, clusters) -> Dict[str, WalletClusterMetrics]
def build_clusters(trades, min_co_trades=3, window_ms=60000) -> Dict[str, WalletClusterMetrics]
```

### 2. Pipeline Orchestration (`ingestion/pipelines/wallet_cluster_pipeline.py`)

```python
class WalletClusterPipeline:
    def run(self, input_path, output_path, dry_run=False, summary_json=False)
```

### 3. Schema Extension

New optional fields in `wallet_profile_schema.json`:

```json
{
  "cluster_label": {"type": ["integer", "null"], "minimum": 0},
  "leader_score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
  "follower_lag_ms": {"type": ["integer", "null"], "minimum": 0},
  "co_trade_count": {"type": ["integer", "null"], "minimum": 0}
}
```

## Fixtures

`integration/fixtures/discovery/trades_norm_co_trade_sample.jsonl`:

- 12 trades (3 wallets × 4 tokens)
- W1: Leader (always first, ts=0)
- W2: Follower (15-45s after W1)
- W3: Outsider (90s+ after, not clustered)

Expected result:
- Cluster 0: {W1, W2} (co-trades on all 4 tokens)
- Cluster 1: {W3} (no co-trades)

## Usage

```bash
# Run clustering pipeline
python3 -m ingestion.pipelines.wallet_cluster_pipeline \
    --input trades_norm.parquet \
    --output wallets_clustered.parquet \
    --dry-run \
    --summary-json

# Skip clustering in discovery
python3 integration/wallet_discovery.py --skip-clustering ...
```

## Hard Rules

| Rule | Description |
|------|-------------|
| Pure Functions | No side effects in graph logic |
| Deterministic | Same input → same output |
| Optional Fields | New fields are nullable |
| Backward Compatibility | `--skip-clustering` disables without errors |

## Smoke Test

```bash
bash scripts/wallet_graph_smoke.sh
```

Expected output:
```
[overlay_lint] running wallet_graph smoke...
[wallet_graph_smoke] built co-trade graph: 3 wallets, 2 clusters
[wallet_graph_smoke] OK
```

## GREP Points

```bash
grep -n "build_co_trade_matrix" analysis/wallet_graph.py        # Line ~50
grep -n "detect_clusters" analysis/wallet_graph.py              # Line ~100
grep -n "leader_score" strategy/schemas/wallet_profile_schema.json  # (to be added)
grep -n "clusters_count" ingestion/pipelines/wallet_cluster_pipeline.py  # Line ~150
grep -n "PR-WD.4" strategy/docs/overlay/PR_WD4_WALLET_GRAPH.md  # Line 1
grep -n "\[wallet_graph_smoke\] OK" scripts/wallet_graph_smoke.sh  # Line ~50
grep -n "--skip-clustering" integration/wallet_discovery.py   # (to be added)
```
