#!/bin/bash
# Smoke test wrapper for Feature Wiring (PR-C.6)
# Usage: bash scripts/features_wiring_smoke.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running features wiring smoke..."

python3 scripts/features_wiring_smoke.py
