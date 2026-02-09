#!/bin/bash
# scripts/coordination_smoke.sh

set -e

echo "[overlay_lint] running coordination detector smoke..."

cd "$(dirname "$0")/.."

python3 scripts/coordination_test_clustered.py
python3 scripts/coordination_test_random.py
python3 scripts/coordination_test_disabled.py
python3 scripts/coordination_test_determinism.py

echo "[coordination_smoke] OK"
