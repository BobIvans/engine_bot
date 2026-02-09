#!/bin/bash
# Smoke test wrapper for Latency-Aware Cost Estimator (PR-R.1)
# Usage: bash scripts/latency_smoke.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running latency smoke..."

python3 scripts/latency_smoke.py
