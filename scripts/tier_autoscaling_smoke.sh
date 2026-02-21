#!/bin/bash
# Smoke test for Wallet Tier Auto-Scaling
# Tests: Promote/Demote logic, config generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE_DIR="$PROJECT_ROOT/integration/fixtures/tiers_autoscaling"
OUTPUT_CHANGES="/tmp/tier_changes.jsonl"
OUTPUT_CONFIG="/tmp/wallet_tiers.next.yaml"

echo "[tier_autoscaling_smoke] Starting tier autoscaling smoke test..." >&2

# Clean up any previous output
rm -f "$OUTPUT_CHANGES" "$OUTPUT_CONFIG"

# Run autoscaling stage
echo "[tier_autoscaling_smoke] Running autoscaler..." >&2
python3 -m integration.tier_autoscaling_stage \
    --current "$FIXTURE_DIR/current_tiers.yaml" \
    --metrics "$FIXTURE_DIR/performance_metrics.jsonl" \
    --out-changes "$OUTPUT_CHANGES" \
    --out-config "$OUTPUT_CONFIG" \
    --verbose > /dev/null

# Verify output files exist
if [ ! -f "$OUTPUT_CHANGES" ]; then
    echo "[tier_autoscaling_smoke] FAIL: Change log not created" >&2
    exit 1
fi

if [ ! -f "$OUTPUT_CONFIG" ]; then
    echo "[tier_autoscaling_smoke] FAIL: New config not created" >&2
    exit 1
fi

# Test 1: Verify WalletA (Tier 1 -> Demote)
echo "[tier_autoscaling_smoke] Verifying WalletA demotion..." >&2
DEMOTE_CHECK=$(grep "WalletA" "$OUTPUT_CHANGES" | grep "DEMOTE")
if [ -z "$DEMOTE_CHECK" ]; then
    echo "[tier_autoscaling_smoke] FAIL: WalletA should be demoted (Low ROI)" >&2
    exit 1
fi
echo "[tier_autoscaling_smoke] WalletA demoted ✓" >&2

# Test 2: Verify WalletB (Tier 2 -> Promote)
echo "[tier_autoscaling_smoke] Verifying WalletB promotion..." >&2
PROMOTE_CHECK=$(grep "WalletB" "$OUTPUT_CHANGES" | grep "PROMOTE")
if [ -z "$PROMOTE_CHECK" ]; then
    echo "[tier_autoscaling_smoke] FAIL: WalletB should be promoted (High ROI/WR)" >&2
    exit 1
fi
echo "[tier_autoscaling_smoke] WalletB promoted ✓" >&2

# Test 3: Verify new config structure
echo "[tier_autoscaling_smoke] Verifying new config structure..." >&2
# WalletB should be in tier_1
if ! grep -A 5 "tier_1:" "$OUTPUT_CONFIG" | grep -q "WalletB"; then
    echo "[tier_autoscaling_smoke] FAIL: WalletB not found in new tier_1 config" >&2
    exit 1
fi

# WalletA should be in tier_3 (demoted from 1)
if ! grep -A 5 "tier_3:" "$OUTPUT_CONFIG" | grep -q "WalletA"; then
    echo "[tier_autoscaling_smoke] FAIL: WalletA not found in new tier_3 config" >&2
    exit 1
fi
echo "[tier_autoscaling_smoke] New config structure verified ✓" >&2

# Cleanup
rm -f "$OUTPUT_CHANGES" "$OUTPUT_CONFIG"

echo "[tier_autoscaling_smoke] All autoscaling tests passed!" >&2
echo "[tier_autoscaling_smoke] OK ✅"
