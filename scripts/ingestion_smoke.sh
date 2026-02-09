#!/usr/bin/env bash
set -euo pipefail

# scripts/ingestion_smoke.sh
# Smoke test for PR-A.3 Historical Data Ingestion

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[ingestion_smoke] Starting smoke tests..." >&2

# ============================================
# Test 1: ingest_history.py on dune_sample.csv
# ============================================
echo "[ingestion_smoke] Testing ingest_history.py..." >&2

INPUT_CSV="integration/fixtures/dune_sample.csv"
OUTPUT_PARQUET="/tmp/ingestion_smoke_test.parquet"

# Clean up any previous test output
rm -f "$OUTPUT_PARQUET"

# Run the ingestion tool
python3 -m tools.ingest_history \
    --input "$INPUT_CSV" \
    --format dune \
    --out "$OUTPUT_PARQUET" \
    2>&1

# Verify output Parquet exists
if [[ ! -f "$OUTPUT_PARQUET" ]]; then
    echo "ERROR: ingestion_smoke: output Parquet not created" >&2
    exit 1
fi

echo "[ingestion_smoke] Verifying Parquet schema and row count..." >&2

# Verify row count (dune_sample.csv has 3 data rows)
ROW_COUNT=$(python3 -c "import duckdb; con = duckdb.connect('$OUTPUT_PARQUET'); print(con.execute('SELECT COUNT(*) FROM read_parquet(\"$OUTPUT_PARQUET\")').fetchone()[0])")

if [[ "$ROW_COUNT" -ne 3 ]]; then
    echo "ERROR: ingestion_smoke: expected 3 rows, got $ROW_COUNT" >&2
    exit 1
fi

echo "[ingestion_smoke] Row count verified: $ROW_COUNT" >&2

# Verify schema has required columns
REQUIRED_COLUMNS=("ts" "wallet" "mint" "side" "price" "size_usd" "tx_hash")
for col in "${REQUIRED_COLUMNS[@]}"; do
    COLUMN_EXISTS=$(python3 -c "import duckdb; con = duckdb.connect('$OUTPUT_PARQUET'); cols = con.execute('SELECT column_names FROM read_parquet(\"$OUTPUT_PARQUET\") LIMIT 1').fetchone()[0]; print('$col' in cols)")
    if [[ "$COLUMN_EXISTS" != "True" ]]; then
        echo "ERROR: ingestion_smoke: missing required column: $col" >&2
        exit 1
    fi
done

echo "[ingestion_smoke] Schema verified with required columns" >&2

# Clean up
rm -f "$OUTPUT_PARQUET"

# ============================================
# Test 2: update_tier1_wallets.py on dummy CSV
# ============================================
echo "[ingestion_smoke] Testing update_tier1_wallets.py..." >&2

# Create a dummy CSV with wallet addresses
DUMMY_CSV="/tmp/ingestion_smoke_wallets.csv"
OUTPUT_YAML="/tmp/ingestion_smoke_wallets.yaml"

# Clean up any previous test output
rm -f "$DUMMY_CSV" "$OUTPUT_YAML"

# Create dummy CSV with valid Solana wallet addresses
cat > "$DUMMY_CSV" << 'EOF'
wallet_address
So11111111111111111111111111111111111111112
EpSZ2ys5DHZYd1g8tQBhL6v1v7zT9vYrV9m3K3w9vZxY
7N4yJZJv8XQk8YVdYvJt9wG5v9v9vYrV9m3K3w9vZxY
EOF

# Run the wallet updater tool
python3 -m tools.update_tier1_wallets \
    --input "$DUMMY_CSV" \
    --out "$OUTPUT_YAML" \
    2>&1

# Verify output YAML exists
if [[ ! -f "$OUTPUT_YAML" ]]; then
    echo "ERROR: ingestion_smoke: output YAML not created" >&2
    exit 1
fi

echo "[ingestion_smoke] Verifying YAML output..." >&2

# Verify YAML contains tier1_wallets key
if ! python3 -c "import yaml; d = yaml.safe_load(open('$OUTPUT_YAML')); 'tier1_wallets' in d" 2>/dev/null; then
    echo "ERROR: ingestion_smoke: YAML missing tier1_wallets key" >&2
    exit 1
fi

# Verify wallet count (should be 3 valid wallets)
WALLET_COUNT=$(python3 -c "import yaml; d = yaml.safe_load(open('$OUTPUT_YAML')); print(len(d.get('tier1_wallets', [])))")

if [[ "$WALLET_COUNT" -ne 3 ]]; then
    echo "ERROR: ingestion_smoke: expected 3 wallets, got $WALLET_COUNT" >&2
    exit 1
fi

echo "[ingestion_smoke] Wallet count verified: $WALLET_COUNT" >&2

# Clean up
rm -f "$DUMMY_CSV" "$OUTPUT_YAML"

echo "[ingestion_smoke] All smoke tests passed!" >&2
echo "[ingestion_smoke] OK ✅"
