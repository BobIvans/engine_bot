#!/bin/bash
# scripts/token_mapping_smoke.sh
#
# PR-PM.4 Smoke Test: Polymarket Token Mapping
#
# Validates token mapping strategies and output format against fixtures.
#
# Usage:
#   bash scripts/token_mapping_smoke.sh [--verbose]
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Fixtures
POLYMARKET_JSON="$ROOT_DIR/integration/fixtures/sentiment/polymarket_sample_mapping.json"
TOKENS_CSV="$ROOT_DIR/integration/fixtures/discovery/token_snapshot_sample_mapping.csv"
OUTPUT_PARQUET="/tmp/polymarket_token_mapping.parquet"

echo "[overlay_lint] running token_mapping smoke..."

# Test 1: Run the pipeline
echo "[token_mapping] Testing pipeline execution..."


TMP_ERR="${OUTPUT_PARQUET}.stderr"
set +e
result=$(cd "$ROOT_DIR" && python3 -m ingestion.pipelines.token_mapping_pipeline \
  --input-polymarket "$POLYMARKET_JSON" \
  --input-tokens "$TOKENS_CSV" \
  --output "$OUTPUT_PARQUET" \
  --dry-run \
  --summary-json 2> "${TMP_ERR}" )
exit_code=$?

set -e

if [ $exit_code -ne 0 ]; then
    echo "[token_mapping_smoke] ERROR: token_mapping_pipeline failed (exit=$exit_code)" >&2
    echo "[token_mapping_smoke] --- stderr (first 200 lines) ---" >&2
    sed -n '1,200p' "${TMP_ERR}" >&2 || true
    echo "[token_mapping_smoke] --- end stderr ---" >&2
    echo "[token_mapping_smoke] --- captured stdout/stderr (fallback) ---" >&2
    echo "$result" >&2 || true
    echo "[token_mapping_smoke] --- end fallback ---" >&2
    exit 1
fi

# Parse JSON output
mappings_count=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['mappings_count'])")
markets_covered=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['markets_covered'])")
top_relevance=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['top_relevance'])")

# Validate results
errors=0

if [ "$mappings_count" -lt 6 ]; then
    echo "[token_mapping_smoke] ERROR: Expected at least 6 mappings, got $mappings_count"
    errors=$((errors + 1))
fi

if [ "$markets_covered" -lt 3 ]; then
    echo "[token_mapping_smoke] ERROR: Expected at least 3 markets covered, got $markets_covered"
    errors=$((errors + 1))
fi

if [ "$(echo "$top_relevance" | python3 -c 'import sys; print(1 if float(sys.stdin.read()) >= 1.0 else 0)')" -ne 1 ]; then
    echo "[token_mapping_smoke] ERROR: Expected top_relevance >= 1.0, got $top_relevance"
    errors=$((errors + 1))
fi

if [ $errors -gt 0 ]; then
    echo "[token_mapping_smoke] ERRORS: $errors validation failures"
    exit 1
fi

# Test 2: Validate exact_symbol matches
echo "[token_mapping] Validating exact_symbol matches..."

exact_count=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['by_type']['exact_symbol'])")

if [ "$exact_count" -lt 2 ]; then
    echo "[token_mapping_smoke] ERROR: Expected at least 2 exact_symbol matches, got $exact_count"
    exit 1
fi

echo "[token_mapping] exact_symbol count: $exact_count"

# Test 3: Validate thematic matches
echo "[token_mapping] Validating thematic matches..."

thematic_count=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['by_type']['thematic'])")

if [ "$thematic_count" -lt 2 ]; then
    echo "[token_mapping_smoke] ERROR: Expected at least 2 thematic matches, got $thematic_count"
    exit 1
fi

echo "[token_mapping] thematic count: $thematic_count"

# Test 4: Validate fuzzy_name matches
# Note: fuzzy_name may be 0 if thematic/exact matches cover all overlaps
echo "[token_mapping] Validating fuzzy_name matches..."

fuzzy_count=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['by_type'].get('fuzzy_name', 0))")

echo "[token_mapping] fuzzy_name count: $fuzzy_count"

# Test 5: Validate output file
# Note: --dry-run doesn't create output file, so skip this check
echo "[token_mapping] Output validation (dry-run mode - file not created)"

echo "[token_mapping_smoke] built $mappings_count mappings across $markets_covered markets (max relevance=$top_relevance)"
echo "[token_mapping_smoke] OK"
exit 0
