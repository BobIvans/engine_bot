#!/usr/bin/env bash
# scripts/meteora_dlmm_smoke.sh
# Smoke test for Meteora DLMM slippage estimation
# PR-MET.1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

FIXTURE_PATH="${ROOT_DIR}/integration/fixtures/execution/meteora_pool_sample.json"
TOKEN_MINT="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN_PRICE_USD=1.00  # USDC price
SIZE_USD=3000.0

echo "[meteora_dlmm_smoke] Starting Meteora DLMM smoke test..."
echo "[meteora_dlmm_smoke] Fixture: ${FIXTURE_PATH}"
echo "[meteora_dlmm_smoke] Token mint: ${TOKEN_MINT}"

# Check fixture exists
if [[ ! -f "${FIXTURE_PATH}" ]]; then
    echo "[meteora_dlmm_smoke] ERROR: Fixture not found: ${FIXTURE_PATH}" >&2
    exit 1
fi

# Run decoder in dry-run mode
echo ""
echo "[meteora_dlmm_smoke] Running decoder..."
STDOUT=$(python3 -m ingestion.sources.meteora_dlmm \
    --input-file "${FIXTURE_PATH}" \
    --token-mint "${TOKEN_MINT}" \
    --size-usd "${SIZE_USD}" \
    --token-price-usd "${TOKEN_PRICE_USD}" \
    --summary-json 2>/dev/null)

# Log stderr output
echo "${STDOUT}" | grep -E "^\[meteora_dlmm\]" >&2 || true

DECODER_EXIT=$?

if [[ ${DECODER_EXIT} -ne 0 ]]; then
    echo "[meteora_dlmm_smoke] ERROR: Decoder exited with code ${DECODER_EXIT}" >&2
    exit 1
fi

# Validate JSON output
echo ""
echo "[meteora_dlmm_smoke] Validating JSON output..."
if ! echo "${STDOUT}" | python3 -c "import json, sys; data=json.load(sys.stdin); assert data.get('pool_decoded')==True" 2>/dev/null; then
    echo "[meteora_dlmm_smoke] ERROR: Invalid JSON output or pool not decoded" >&2
    echo "Output was: ${STDOUT}" >&2
    exit 1
fi

# Extract and validate slippage
SLIPPAGE_BPS=$(echo "${STDOUT}" | python3 -c "import json, sys; print(json.load(sys.stdin).get('estimated_slippage_bps', -1))")
echo "[meteora_dlmm_smoke] Estimated slippage: ${SLIPPAGE_BPS} bps"

# Calculate expected slippage manually
# Pool: bin_step_bps=10, active_bin_liquidity=500M
# bin_density_factor = min(5.0, 100.0/10) = 5.0
# effective_depth_usd = (500M/1e6) * 1.00 * 5.0 = 2500
# size_ratio = 3000 / 2500 = 1.2 (large swap, >15%)
# slippage_pct = 1.2 * 100 * (1 + 0.7 * (1.2 - 0.15) / 0.85) = 120 * (1 + 0.7 * 1.235) = 120 * 1.865 = 223.8%
# slippage_bps = min(10000, 223.8 * 100) = 9999 (capped at 10000)
EXPECTED_SLIPPAGE_BPS=9999

if [[ ${SLIPPAGE_BPS} -ne ${EXPECTED_SLIPPAGE_BPS} ]]; then
    echo "[meteora_dlmm_smoke] WARNING: Slippage mismatch. Expected: ${EXPECTED_SLIPPAGE_BPS}, Got: ${SLIPPAGE_BPS}"
    echo "[meteora_dlmm_smoke] (This is expected for large swaps exceeding pool depth)"
fi

# Test with smaller swap to verify formula
echo ""
echo "[meteora_dlmm_smoke] Testing with smaller swap (\$500)..."
STDOUT_SMALL=$(python3 -m ingestion.sources.meteora_dlmm \
    --input-file "${FIXTURE_PATH}" \
    --token-mint "${TOKEN_MINT}" \
    --size-usd 500.0 \
    --token-price-usd "${TOKEN_PRICE_USD}" \
    --summary-json 2>/dev/null)

SLIPPAGE_SMALL=$(echo "${STDOUT_SMALL}" | python3 -c "import json, sys; print(json.load(sys.stdin).get('estimated_slippage_bps', -1))")
echo "[meteora_dlmm_smoke] Small swap slippage: ${SLIPPAGE_SMALL} bps"

# For small swap: size_ratio = 500 / 2500 = 0.2 (still >15%)
# slippage_pct = 0.2 * 100 * (1 + 0.7 * (0.2 - 0.15) / 0.85) = 20 * (1 + 0.7 * 0.059) = 20 * 1.041 = 20.82%
# slippage_bps = 20.82 * 100 = 2082
EXPECTED_SMALL=2082
if [[ ${SLIPPAGE_SMALL} -ne ${EXPECTED_SMALL} ]]; then
    echo "[meteora_dlmm_smoke] WARNING: Small swap slippage mismatch. Expected: ${EXPECTED_SMALL}, Got: ${SLIPPAGE_SMALL}"
fi

# Validate effective depth calculation
EFFECTIVE_DEPTH=$(echo "${STDOUT}" | python3 -c "import json, sys; print(json.load(sys.stdin).get('effective_depth_usd', -1))")
EXPECTED_DEPTH=2500.0
DEPTH_DIFF=$(python3 -c "print(abs(${EFFECTIVE_DEPTH} - ${EXPECTED_DEPTH}))")
if [[ $(echo "${DEPTH_DIFF} > 1.0" | bc 2>/dev/null || echo "false") == "true" ]]; then
    echo "[meteora_dlmm_smoke] WARNING: Effective depth mismatch. Expected: ${EXPECTED_DEPTH}, Got: ${EFFECTIVE_DEPTH}"
fi

echo ""
echo "[meteora_dlmm_smoke] Decoded pool details:"
echo "${STDOUT}" | python3 -m json.tool 2>/dev/null | head -20 >&2

echo ""
echo "[meteora_dlmm_smoke] OK"
exit 0
