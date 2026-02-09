#!/bin/bash
# scripts/train_model_smoke.sh
# PR-C.4 ML Training Pipeline Smoke Test

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[train_model_smoke] Starting ML Training Pipeline smoke test..." >&2

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Step 1: Export training dataset
echo "[train_model_smoke] Exporting training dataset..." >&2
python3 << 'PYTHON_EXPORT'
import sys
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

import json
from integration.token_snapshot_store import TokenSnapshotStore
from integration.trade_normalizer import normalize_trade_record
from integration.wallet_profile_store import WalletProfileStore

# Load snapshots
snap_store = TokenSnapshotStore.from_csv(
    "/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/token_snapshot.v2.csv"
)

# Create a minimal dataset from sample trades
trades_jsonl = "/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/trades.sample.jsonl"
with open(trades_jsonl, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        print(line)
PYTHON_EXPORT

echo "[train_model_smoke] Running exporter..." >&2

# Use the exporter to create the dataset
python3 "/Users/ivansbobrovs/Downloads/strategy pack/tools/export_training_dataset.py" \
    --trades-jsonl "/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/trades.sample.jsonl" \
    --token-snapshot "/Users/ivansbobrovs/Downloads/strategy pack/integration/fixtures/token_snapshot.v2.csv" \
    --out-parquet "$TEMP_DIR/dataset.parquet" \
    --label-horizon-sec 300 \
    --coverage-stderr

if [ ! -f "$TEMP_DIR/dataset.parquet" ]; then
    echo "[train_model_smoke] FAIL: Dataset not created" >&2
    exit 1
fi

echo "[train_model_smoke] Dataset created: $TEMP_DIR/dataset.parquet" >&2

# Step 2: Train model
echo "[train_model_smoke] Training XGBoost model..." >&2

python3 "/Users/ivansbobrovs/Downloads/strategy pack/models/train_xgboost.py" \
    --dataset "$TEMP_DIR/dataset.parquet" \
    --out-dir "$TEMP_DIR/artifacts" \
    --target-roi-pct 0.0

# Step 3: Verify artifacts
echo "[train_model_smoke] Verifying artifacts..." >&2

if [ ! -f "$TEMP_DIR/artifacts/model.json" ]; then
    echo "[train_model_smoke] FAIL: model.json not found" >&2
    exit 1
fi

if [ ! -f "$TEMP_DIR/artifacts/metrics.json" ]; then
    echo "[train_model_smoke] FAIL: metrics.json not found" >&2
    exit 1
fi

# Verify metrics.json has required keys
python3 << 'PYTHON_VERIFY'
import sys
import json

metrics_path = sys.argv[1]
with open(metrics_path, "r") as f:
    metrics = json.load(f)

required_keys = ["precision", "recall", "auc"]
missing = [k for k in required_keys if k not in metrics]
if missing:
    print(f"[train_model_smoke] FAIL: metrics.json missing keys: {missing}", file=sys.stderr)
    sys.exit(1)

print(f"[train_model_smoke] Metrics verified: precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, auc={metrics['auc']:.4f}", file=sys.stderr)
PYTHON_VERIFY "$TEMP_DIR/artifacts/metrics.json"

# Verify model.json is valid JSON
python3 << 'PYTHON_MODEL'
import sys
import json

model_path = sys.argv[1]
with open(model_path, "r") as f:
    model = json.load(f)

# XGBoost model.json should have 'learner' key
if "learner" not in model and "model" not in model:
    print(f"[train_model_smoke] FAIL: model.json does not appear to be valid XGBoost format", file=sys.stderr)
    sys.exit(1)

print(f"[train_model_smoke] Model verified: valid XGBoost JSON format", file=sys.stderr)
PYTHON_MODEL "$TEMP_DIR/artifacts/model.json"

echo "[train_model_smoke] ALL CHECKS PASSED" >&2
echo "[train_model_smoke] OK ✅" >&2
exit 0
