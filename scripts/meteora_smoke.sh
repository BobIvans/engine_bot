#!/bin/bash
# scripts/meteora_smoke.sh
# Smoke test for Meteora DLMM Adapter
# PR-U.3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
python3 scripts/meteora_smoke.py
