#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[live_snapshot_smoke] Testing PR-F.2 Live Token Snapshot Store..." >&2

# Create a temporary Python test script that monkey-patches requests.get
# to return the mock Jupiter response

MOCK_SCRIPT=$(mktemp)
trap 'rm -f "$MOCK_SCRIPT"' RETURN

cat > "$MOCK_SCRIPT" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""Smoke test for LiveTokenSnapshotStore using mock Jupiter response."""
import json
import sys
import os
import types

# Ensure the project root is in the Python path
sys.path.insert(0, os.getcwd())

def log(msg):
    print(f"[live_snapshot_smoke] {msg}", file=sys.stderr)

# Create a mock requests module before anything imports it
mock_requests = types.ModuleType("requests")

class MockResponse:
    def __init__(self, data):
        self._data = data
    def json(self):
        return self._data
    def raise_for_status(self):
        pass
    @property
    def status_code(self):
        return 200

# Create a mock RequestException
class RequestException(Exception):
    pass

mock_requests.RequestException = RequestException
mock_requests.get = None
mock_requests.Response = MockResponse

# Create mock exceptions module
mock_exceptions = types.ModuleType("requests.exceptions")
mock_exceptions.RequestException = RequestException
sys.modules["requests.exceptions"] = mock_exceptions
sys.modules["requests"] = mock_requests

# Load the mock response
MOCK_RESPONSE_PATH = "integration/fixtures/jupiter_mock_response.json"
with open(MOCK_RESPONSE_PATH, "r") as f:
    MOCK_DATA = json.load(f)

def mock_get(url, **kwargs):
    return MockResponse(MOCK_DATA)

# Now apply the patches
import requests
requests.get = mock_get

# Import and test LiveTokenSnapshotStore
from integration.live_snapshot_store import LiveTokenSnapshotStore

log("Creating LiveTokenSnapshotStore instance...")

store = LiveTokenSnapshotStore(ttl_seconds=30)

# Test with a sample token mint from the mock response
TEST_MINT = "So11111111111111111111111111111111111111112"  # SOL

log(f"Testing get() for mint: {TEST_MINT}")

result = store.get(TEST_MINT)

# Validate the result
log("Validating result...")

if result is None:
    log("FAIL: get() returned None")
    sys.exit(1)

# Check that result is a TokenSnapshot with expected fields
if not hasattr(result, 'mint'):
    log("FAIL: result missing 'mint' attribute")
    sys.exit(1)

if result.mint != TEST_MINT:
    log(f"FAIL: mint mismatch, expected {TEST_MINT}, got {result.mint}")
    sys.exit(1)

if result.ts_snapshot is None:
    log("FAIL: ts_snapshot is None")
    sys.exit(1)

# Check that extra contains price data from Jupiter
if result.extra is None:
    log("FAIL: extra is None")
    sys.exit(1)

if 'price' not in result.extra:
    log("FAIL: 'price' not in extra")
    sys.exit(1)

expected_price = 1.23
actual_price = result.extra['price']
if actual_price != expected_price:
    log(f"FAIL: price mismatch, expected {expected_price}, got {actual_price}")
    sys.exit(1)

# Check that jupiter_raw is present
if 'jupiter_raw' not in result.extra:
    log("FAIL: 'jupiter_raw' not in extra")
    sys.exit(1)

# Check liquidity_usd is None (Jupiter price API doesn't provide it)
if result.liquidity_usd is not None:
    log(f"FAIL: liquidity_usd should be None, got {result.liquidity_usd}")
    sys.exit(1)

log(f"Result: mint={result.mint}, price={result.extra.get('price')}, ts_snapshot={result.ts_snapshot}")

# Test cache functionality - second call should return cached result
log("Testing cache functionality...")

result2 = store.get(TEST_MINT)

if result2 is None:
    log("FAIL: second get() returned None")
    sys.exit(1)

if result2.mint != TEST_MINT:
    log("FAIL: cached result mint mismatch")
    sys.exit(1)

log("Cache test passed")

# Test with another mint to ensure different requests
TEST_MINT_2 = "JUPyiwrYJFskUPiHa7hkeR8VUtkqjberbSOWd91pbT2"  # JUP

log(f"Testing get() for mint: {TEST_MINT_2}")

result3 = store.get(TEST_MINT_2)

if result3 is None:
    log("FAIL: get() for JUP returned None")
    sys.exit(1)

if result3.extra.get('price') != 2.45:
    log(f"FAIL: JUP price mismatch, expected 2.45, got {result3.extra.get('price')}")
    sys.exit(1)

log("All tests passed!")
PYTHON_SCRIPT

# Run the mock test
echo "[live_snapshot_smoke] Running LiveTokenSnapshotStore mock test..." >&2

tmp_out=$(mktemp)
trap 'rm -f "$tmp_out"' RETURN

# Run the mock test script and capture output
python3 "$MOCK_SCRIPT" >"$tmp_out" 2>&1 || {
    echo "[live_snapshot_smoke] FAIL: Mock test exited with non-zero code" >&2
    cat "$tmp_out" >&2
    exit 1
}

# All logs go to stderr, only the final result line goes to stdout
cat "$tmp_out" >&2

echo "[live_snapshot_smoke] OK ✅"
