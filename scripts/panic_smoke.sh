#!/usr/bin/env bash
#
# Smoke test for ops/panic.py module.
# Tests the kill-switch mechanism by creating/removing the sentinel file.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "[overlay_lint] running panic smoke..."

python3 - <<'PY'
import os
import tempfile
from pathlib import Path

from ops.panic import (
    is_panic_active,
    create_panic_flag,
    clear_panic_flag,
    require_no_panic,
    PanicShutdown,
)

tmpdir = Path(tempfile.mkdtemp(prefix="panic_smoke_"))
sentinel = tmpdir / "PANIC"

# 1) default: not active
assert is_panic_active(str(sentinel)) is False
print("[panic_smoke] Test 1 PASS: default not active")

# 2) create flag -> active
create_panic_flag(str(sentinel))
assert sentinel.exists()
assert is_panic_active(str(sentinel)) is True
print("[panic_smoke] Test 2 PASS: create -> active")

# 3) require_no_panic should raise when active
raised = False
try:
    require_no_panic(str(sentinel))
except PanicShutdown:
    raised = True
assert raised, "require_no_panic did not raise PanicShutdown"
print("[panic_smoke] Test 3 PASS: require_no_panic raises when active")

# 4) clear flag -> inactive
clear_panic_flag(str(sentinel))
assert sentinel.exists() is False
assert is_panic_active(str(sentinel)) is False
print("[panic_smoke] Test 4 PASS: clear -> inactive")

# 5) require_no_panic should pass when inactive
require_no_panic(str(sentinel))
print("[panic_smoke] Test 5 PASS: require_no_panic passes when inactive")

print("[panic_smoke] OK ✅")
PY

echo "[panic_smoke] Smoke test completed."
