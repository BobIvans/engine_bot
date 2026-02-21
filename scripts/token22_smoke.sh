#!/bin/bash
# Smoke test for Token-2022 Extension Scanner
# Tests: extension analysis, risk flag detection, blocking logic

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/token22"
OUTPUT_FILE="/tmp/token_extensions.jsonl"

echo "[token22_smoke] Starting Token-2022 extension scanner smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_FILE"

# Run token22 stage
echo "[token22_smoke] Running extension scanner..." >&2
python3 -m integration.token22_stage \
    --mints "$FIXTURE_DIR/mints.jsonl" \
    --account-data "$FIXTURE_DIR/account_data.json" \
    --out "$OUTPUT_FILE" \
    --verbose > /dev/null

# Verify output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "[token22_smoke] FAIL: Output file not created" >&2
    exit 1
fi

# Test 1: Verify CleanMint111 has CLEAN flag and is not blocked
echo "[token22_smoke] Verifying clean token..." >&2
CLEAN_FLAGS=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'CleanMint111':
        print(','.join(d['risk_flags']))
")
CLEAN_BLOCKED=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'CleanMint111':
        print(d['is_blocked'])
")

if [[ "$CLEAN_FLAGS" != "CLEAN" ]]; then
    echo "[token22_smoke] FAIL: CleanMint111 should have CLEAN flag, got '$CLEAN_FLAGS'" >&2
    exit 1
fi

if [[ "$CLEAN_BLOCKED" != "False" ]]; then
    echo "[token22_smoke] FAIL: CleanMint111 should not be blocked, got is_blocked=$CLEAN_BLOCKED" >&2
    exit 1
fi
echo "[token22_smoke] CleanMint111: flags=$CLEAN_FLAGS, is_blocked=$CLEAN_BLOCKED" >&2

# Test 2: Verify HookMint222 has HAS_TRANSFER_HOOK flag and is blocked
echo "[token22_smoke] Verifying TransferHook token..." >&2
HOOK_FLAGS=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'HookMint222':
        print(','.join(d['risk_flags']))
")
HOOK_BLOCKED=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'HookMint222':
        print(d['is_blocked'])
")

if [[ "$HOOK_FLAGS" != *"HAS_TRANSFER_HOOK"* ]]; then
    echo "[token22_smoke] FAIL: HookMint222 should have HAS_TRANSFER_HOOK flag, got '$HOOK_FLAGS'" >&2
    exit 1
fi

if [[ "$HOOK_BLOCKED" != "True" ]]; then
    echo "[token22_smoke] FAIL: HookMint222 should be blocked, got is_blocked=$HOOK_BLOCKED" >&2
    exit 1
fi
echo "[token22_smoke] HookMint222: flags=$HOOK_FLAGS, is_blocked=$HOOK_BLOCKED" >&2

# Test 3: Verify DelegateMint333 has multiple risk flags and is blocked
echo "[token22_smoke] Verifying PermanentDelegate token..." >&2
DELEGATE_FLAGS=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'DelegateMint333':
        print(','.join(d['risk_flags']))
")
DELEGATE_BLOCKED=$(python3 -c "
import json
for line in open('$OUTPUT_FILE'):
    d = json.loads(line)
    if d['mint'] == 'DelegateMint333':
        print(d['is_blocked'])
")

if [[ "$DELEGATE_FLAGS" != *"HAS_PERMANENT_DELEGATE"* ]]; then
    echo "[token22_smoke] FAIL: DelegateMint333 should have HAS_PERMANENT_DELEGATE flag" >&2
    exit 1
fi

if [[ "$DELEGATE_BLOCKED" != "True" ]]; then
    echo "[token22_smoke] FAIL: DelegateMint333 should be blocked" >&2
    exit 1
fi
echo "[token22_smoke] DelegateMint333: flags=$DELEGATE_FLAGS, is_blocked=$DELEGATE_BLOCKED" >&2

# Test 4: Verify summary contains correct version
echo "[token22_smoke] Verifying output format..." >&2
SUMMARY=$(python3 -m integration.token22_stage \
    --mints "$FIXTURE_DIR/mints.jsonl" \
    --account-data "$FIXTURE_DIR/account_data.json" \
    --out "/tmp/token22_verify.jsonl" 2>/dev/null)

VERSION=$(echo "$SUMMARY" | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])")
if [[ "$VERSION" != "token_extensions.v1" ]]; then
    echo "[token22_smoke] FAIL: Expected version 'token_extensions.v1', got '$VERSION'" >&2
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_FILE" "/tmp/token22_verify.jsonl"

echo "[token22_smoke] All Token-2022 extension tests passed!" >&2
echo "[token22_smoke] OK ✅"
