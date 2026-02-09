#!/bin/bash
# Smoke test wrapper for Portfolio State Manager (PR-B.6)
# Usage: bash scripts/state_smoke.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running state smoke..."

python3 scripts/state_smoke.py
