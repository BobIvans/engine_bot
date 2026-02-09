#!/bin/bash
# scripts/hazard_smoke.sh

set -e

echo "[overlay_lint] running hazard smoke..."

cd "$(dirname "$0")/.."

# Create temporary output files
OUTPUT_JSONL=$(mktemp)
REJECTS_JSONL=$(mktemp)
SUMMARY_JSON=$(mktemp)

cleanup() {
    rm -f "$OUTPUT_JSONL" "$REJECTS_JSONL" "$SUMMARY_JSON"
}
trap cleanup EXIT

# Run hazard stage with fixture
python3 -m integration.hazard_stage \
    --input integration/fixtures/hazard/features_sample.jsonl \
    --output "$OUTPUT_JSONL" \
    --enable-hazard-model \
    --hazard-threshold 0.35 \
    --rejects "$REJECTS_JSONL" \
    --summary-json 2>/dev/null > "$SUMMARY_JSON"

# Check summary JSON
if [ ! -s "$SUMMARY_JSON" ]; then
    echo "[hazard_smoke] FAILED: No summary JSON output"
    exit 1
fi

# Validate hazard_score_avg is reasonable
HAZARD_AVG=$(python3 -c "import sys, json; print(json.load(sys.stdin)['hazard_score_avg'])" < "$SUMMARY_JSON")
if [ -z "$HAZARD_AVG" ]; then
    echo "[hazard_smoke] FAILED: Could not parse hazard_score_avg"
    exit 1
fi

# Check hazard_triggered_count
TRIGGERED_COUNT=$(python3 -c "import sys, json; print(json.load(sys.stdin)['hazard_triggered_count'])" < "$SUMMARY_JSON")

# Check rejects count for invalid features
INVALID_COUNT=$(python3 -c "import sys, json; print(json.load(sys.stdin)['invalid_features_count'])" < "$SUMMARY_JSON")

# Validate output file was created
if [ ! -s "$OUTPUT_JSONL" ]; then
    echo "[hazard_smoke] FAILED: Output file is empty"
    exit 1
fi

# Count records in output
OUTPUT_COUNT=$(wc -l < "$OUTPUT_JSONL")
if [ "$OUTPUT_COUNT" -ne 5 ]; then
    echo "[hazard_smoke] FAILED: Expected 5 output records, got $OUTPUT_COUNT"
    exit 1
fi

# Count rejected records
REJECT_COUNT=$(wc -l < "$REJECTS_JSONL")
if [ "$REJECT_COUNT" -ne 1 ]; then
    echo "[hazard_smoke] FAILED: Expected 1 reject (invalid features), got $REJECT_COUNT"
    exit 1
fi

# Validate rejects contain expected reason
if ! grep -q "hazard_features_invalid" "$REJECTS_JSONL"; then
    echo "[hazard_smoke] FAILED: Rejects don't contain hazard_features_invalid reason"
    exit 1
fi

echo "[hazard_smoke] hazard_score_avg: $HAZARD_AVG"
echo "[hazard_smoke] hazard_triggered_count: $TRIGGERED_COUNT"
echo "[hazard_smoke] invalid_features_count: $INVALID_COUNT"

echo "[hazard_smoke] OK"
