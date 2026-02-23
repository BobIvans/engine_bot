#!/bin/bash
# Portable Feature Engineering v2 Smoke Test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[features_v2_smoke] Starting portable smoke test..."

env ROOT_DIR="$ROOT_DIR" python3 <<'PYTHON_TEST'
import os
import sys
import json
from pathlib import Path

root = Path(os.environ["ROOT_DIR"]).resolve()
sys.path.insert(0, str(root))

from features.trade_features import FEATURE_KEYS_V1, FEATURE_KEYS_V2

expected_path = root / "integration" / "fixtures" / "features_v2_expected.json"
expected = json.loads(expected_path.read_text())["keys"]

missing_from_v2 = sorted(set(FEATURE_KEYS_V1) - set(FEATURE_KEYS_V2))
if missing_from_v2:
    raise AssertionError(f"Missing keys from V1: {missing_from_v2[:10]}")

if expected != FEATURE_KEYS_V2:
    raise AssertionError("FEATURE_KEYS_V2 mismatch with expected fixture")

print("[features_v2_smoke] OK")
PYTHON_TEST
