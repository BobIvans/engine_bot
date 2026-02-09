#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[live_ingestion_smoke] Testing PR-F.1 Live Ingestion Source (RPC)..." >&2

# Create a temporary Python test script that monkey-patches requests.post
# to return the mock RPC response, then runs paper_pipeline.py

MOCK_SCRIPT=$(mktemp)
trap 'rm -f "$MOCK_SCRIPT"' RETURN

cat > "$MOCK_SCRIPT" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""Monkey-patch test for RpcSource live ingestion."""
import json
import sys
import os
import types

# Ensure the project root is in the Python path
sys.path.insert(0, os.getcwd())

# Create a mock requests module before anything imports it
mock_requests = types.ModuleType("requests")
mock_session = types.ModuleType("requests.session")
mock_exceptions = types.ModuleType("requests.exceptions")

class MockSession:
    def __init__(self):
        self.post = None
    def close(self):
        pass

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

class ConnectionError(Exception):
    pass

class Timeout(Exception):
    pass

class HTTPError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

mock_exceptions.ConnectionError = ConnectionError
mock_exceptions.Timeout = Timeout
mock_requests.exceptions = mock_exceptions
mock_session.Session = MockSession
mock_requests.post = None
mock_requests.Session = mock_session
mock_requests.HTTPError = HTTPError

sys.modules["requests"] = mock_requests
sys.modules["requests.session"] = mock_session
sys.modules["requests.exceptions"] = mock_exceptions

# Load the mock response
MOCK_RESPONSE_PATH = "integration/fixtures/rpc_mock_response.json"
with open(MOCK_RESPONSE_PATH, "r") as f:
    MOCK_DATA = json.load(f)

def mock_post(url, **kwargs):
    return MockResponse(MOCK_DATA)

def mock_session_post(url, **kwargs):
    return MockResponse(MOCK_DATA)

# Now apply the patches
import requests
requests.post = mock_post

# Import and patch RpcSource
import ingestion.sources.rpc_source as rpc_module

original_init = rpc_module.RpcSource.__init__

def patched_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self._session.post = mock_session_post

rpc_module.RpcSource.__init__ = patched_init

original_make_request = rpc_module.RpcSource._make_request

def patched_make_request(self, method, params=None):
    return MOCK_DATA.get("result", {})

rpc_module.RpcSource._make_request = patched_make_request

try:
    sys.argv = [
        "paper_pipeline.py",
        "--source-type", "rpc",
        "--rpc-url", "http://mock:8899",
        "--tracked-wallets", "So11111111111111111111111111111111111111112",
        "--summary-json",
        "--dry-run",
        "--only-buy",
    ]
    
    from integration import paper_pipeline
    exit_code = paper_pipeline.main()
finally:
    rpc_module.RpcSource.__init__ = original_init
    rpc_module.RpcSource._make_request = original_make_request

print(f"[live_ingestion_smoke] Exit code: {exit_code}")
sys.exit(exit_code)
PYTHON_SCRIPT

# Run the mock test
echo "[live_ingestion_smoke] Running RPC mock test..." >&2

tmp_out=$(mktemp)
trap 'rm -f "$tmp_out"' RETURN

# Run the mock test script and capture output
python3 "$MOCK_SCRIPT" >"$tmp_out" 2>&1 || {
    echo "[live_ingestion_smoke] FAIL: Mock test exited with non-zero code" >&2
    cat "$tmp_out" >&2
    exit 1
}

# Extract the summary JSON line from output using grep
# The summary JSON is the last line that starts with { and ends with }
summary_line=$(grep -E '^\{.*\}$' "$tmp_out" | tail -1)

if [[ -z "$summary_line" ]]; then
    echo "[live_ingestion_smoke] FAIL: No summary JSON found in output" >&2
    echo "Output:" >&2
    cat "$tmp_out" >&2
    exit 1
fi

echo "[live_ingestion_smoke] Found summary JSON: ${summary_line:0:100}..." >&2

# Validate the summary JSON contains mock trade info
echo "[live_ingestion_smoke] Validating summary JSON..." >&2
python3 - "$summary_line" << 'PYTHON_VALIDATE'
import json
import sys

summary = json.loads(sys.argv[1])

# Check that trades were processed
total_lines = summary.get("counts", {}).get("total_lines", 0)

print(f"[live_ingestion_smoke] Processed {total_lines} total lines", file=sys.stderr)

# The mock response should produce at least 1 trade attempt
if total_lines < 1:
    print("[live_ingestion_smoke] FAIL: Expected at least 1 trade from mock response", file=sys.stderr)
    sys.exit(1)

print("[live_ingestion_smoke] Summary validation passed", file=sys.stderr)
PYTHON_VALIDATE

echo "[live_ingestion_smoke] OK ✅"
