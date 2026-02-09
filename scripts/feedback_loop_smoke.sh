#!/bin/bash
# Smoke test wrapper for Stats Feedback Loop (PR-Q.1)
# Usage: bash scripts/feedback_loop_smoke.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running feedback loop smoke..."

python3 scripts/feedback_loop_smoke.py
