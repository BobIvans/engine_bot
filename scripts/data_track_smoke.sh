#!/bin/bash
# scripts/data_track_smoke.sh
# Integration smoke test for Data-Track Orchestrator

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[data_track_smoke] Running data track orchestrator smoke test..." >&2

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Create a simple config for the test
cat > "${TEMP_DIR}/data_track.yaml" << EOF
pipeline:
  inputs:
    pattern: "data/raw/daily_*.csv"
  storage:
    history: "data/processed/trades_history.parquet"
    profiles: "data/processed/wallet_profiles.csv"
staging_path: "${TEMP_DIR}/staging"
storage_path: "${TEMP_DIR}/prod"
EOF

# Create staging directory
mkdir -p "${TEMP_DIR}/staging"

echo "[data_track_smoke] Running orchestrator with dry-run..." >&2

# Run the orchestrator with dry-run
cd "$ROOT_DIR"
set +e
PYTHONPATH="$ROOT_DIR:${PYTHONPATH}" python3 -m tools.data_track_orchestrator --config "${TEMP_DIR}/data_track.yaml" --dry-run 2>&1 | tee "${TEMP_DIR}/output.txt"
set -e

echo "[data_track_smoke] Checking output..." >&2

# Check for expected output
if grep -q "Starting daily pipeline" "${TEMP_DIR}/output.txt"; then
    echo "[data_track_smoke] Pipeline started successfully" >&2
else
    echo -e "${RED}[data_track_smoke] FAIL: Pipeline did not start${NC}" >&2
    exit 1
fi

if grep -q "Step 1/3: Ingestion" "${TEMP_DIR}/output.txt"; then
    echo "[data_track_smoke] Ingestion step completed" >&2
else
    echo -e "${RED}[data_track_smoke] FAIL: Ingestion step missing${NC}" >&2
    exit 1
fi

if grep -q "Step 2/3: Profiling" "${TEMP_DIR}/output.txt"; then
    echo "[data_track_smoke] Profiling step completed" >&2
else
    echo -e "${RED}[data_track_smoke] FAIL: Profiling step missing${NC}" >&2
    exit 1
fi

if grep -q "Pipeline completed successfully" "${TEMP_DIR}/output.txt"; then
    echo "[data_track_smoke] Pipeline completed successfully" >&2
else
    echo -e "${RED}[data_track_smoke] FAIL: Pipeline did not complete successfully${NC}" >&2
    exit 1
fi

echo "[data_track_smoke] All checks passed!" >&2
echo -e "${GREEN}[data_track_smoke] OK ✅${NC}"
