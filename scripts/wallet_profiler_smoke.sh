#!/usr/bin/env bash
set -euo pipefail

# scripts/wallet_profiler_smoke.sh
# Smoke test for PR-A.1 Wallet Profiler

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TRADES_FIXTURE="integration/fixtures/trades.profiling.jsonl"
OUTPUT_CSV="/tmp/wallet_profiler_smoke_output.csv"

# Run the wallet profiler
python3 -m integration.build_wallet_profiles \
    --trades "$TRADES_FIXTURE" \
    --out "$OUTPUT_CSV" \
    2>&1

# Validate output CSV exists
if [[ ! -f "$OUTPUT_CSV" ]]; then
    echo "ERROR: wallet_profiler_smoke: output CSV not created" >&2
    exit 1
fi

# Validate Wallet A has expected metrics
# Wallet A: trades_30d=2, winrate_30d=0.5, roi_30d_pct=2.5
TRADES_A=$(python3 -c "
import csv
with open('$OUTPUT_CSV', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['wallet'] == 'A':
            print(row['trades_30d'])
            break
")

if [[ -z "$TRADES_A" ]]; then
    echo "ERROR: wallet_profiler_smoke: wallet A not found in output" >&2
    exit 1
fi

if [[ "$TRADES_A" != "2" ]]; then
    echo "ERROR: wallet_profiler_smoke: expected trades_30d=2 for wallet A, got '$TRADES_A'" >&2
    exit 1
fi

WINRATE_A=$(python3 -c "
import csv
with open('$OUTPUT_CSV', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['wallet'] == 'A':
            print(row['winrate_30d'])
            break
")

if [[ "$(echo "$WINRATE_A != 0.5" | bc -l)" -eq 1 ]]; then
    echo "ERROR: wallet_profiler_smoke: expected winrate_30d=0.5 for wallet A, got '$WINRATE_A'" >&2
    exit 1
fi

ROI_A=$(python3 -c "
import csv
with open('$OUTPUT_CSV', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['wallet'] == 'A':
            print(row['roi_30d_pct'])
            break
")

if [[ "$(echo "$ROI_A != 2.5" | bc -l)" -eq 1 ]]; then
    echo "ERROR: wallet_profiler_smoke: expected roi_30d_pct=2.5 for wallet A, got '$ROI_A'" >&2
    exit 1
fi

# Cleanup
rm -f "$OUTPUT_CSV"

echo "[wallet_profiler_smoke] OK ✅"
