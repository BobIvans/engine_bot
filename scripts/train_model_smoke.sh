#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[train_model_smoke] Starting ML Training Pipeline smoke test..." >&2
echo "[train_model_smoke] ROOT_DIR=${ROOT_DIR}" >&2

cd "${ROOT_DIR}"

# Deterministic imports (avoid external packs)
unset PYTHONPATH
export PYTHONPATH="${ROOT_DIR}"

EXPORTER="${ROOT_DIR}/tools/export_training_dataset.py"
if [[ ! -f "${EXPORTER}" ]]; then
  echo "[train_model_smoke] ERROR: missing exporter at ${EXPORTER}" >&2
  exit 1
fi
echo "[train_model_smoke] Using exporter: ${EXPORTER}" >&2

TMP_DIR="${TMPDIR:-/tmp}/engine_bot_train_smoke"
mkdir -p "${TMP_DIR}"

TRADES_JSONL="${TMP_DIR}/trades_smoke.jsonl"
OUT_PARQUET="${TMP_DIR}/train_smoke.parquet"
OUT_CSV="${TMP_DIR}/train_smoke.csv"
COVERAGE_JSON="${TMP_DIR}/coverage_smoke.json"

# Minimal v1 trades dataset (2 rows)
cat > "${TRADES_JSONL}" <<'JSONL'
{"schema_version":"trade_v1","ts":"2026-01-05 10:00:00.000","wallet":"SoMeWallet1111111111111111111111111111111111","mint":"So11111111111111111111111111111111111111112","side":"buy","price":100.0,"size_usd":150.0,"platform":"raydium","tx_hash":"tx_001","pool_id":"pool_test_001","honeypot_pass":true,"wallet_roi_30d_pct":35.0,"wallet_winrate_30d":0.62,"wallet_trades_30d":120}
{"schema_version":"trade_v1","ts":"2026-01-05 10:00:02.000","wallet":"SoMeWallet1111111111111111111111111111111111","mint":"So11111111111111111111111111111111111111112","side":"sell","price":102.0,"size_usd":150.0,"platform":"raydium","tx_hash":"tx_002","pool_id":"pool_test_001","honeypot_pass":true,"wallet_roi_30d_pct":35.0,"wallet_winrate_30d":0.62,"wallet_trades_30d":120}
JSONL

rm -f "${OUT_PARQUET}" "${OUT_CSV}" "${COVERAGE_JSON}"
# Make sure repo root is first on sys.path (not /Users/ivansbobrovs)
python3 - <<PY
import os, sys
root = os.path.abspath("${ROOT_DIR}")
sys.path[:] = [root] + [p for p in sys.path if p and p != root and "strategy pack" not in p]
print("[train_model_smoke] sys.path[0:5] =", sys.path[:5], file=sys.stderr)
PY

echo "[train_model_smoke] Running exporter..." >&2
python3 "${EXPORTER}" \
  --trades-jsonl "${TRADES_JSONL}" \
  --out-parquet "${OUT_PARQUET}" \
  --coverage-out "${COVERAGE_JSON}" \
  --coverage-stderr

# Assertions: parquet exists and non-empty
# Accept parquet OR csv (duckdb may be unavailable in CI)
if [[ -f "${OUT_PARQUET}" && -s "${OUT_PARQUET}" ]]; then
  echo "[train_model_smoke] OK: parquet created: ${OUT_PARQUET}" >&2
elif [[ -f "${OUT_CSV}" && -s "${OUT_CSV}" ]]; then
  echo "[train_model_smoke] OK: csv created (duckdb unavailable): ${OUT_CSV}" >&2
else
  echo "[train_model_smoke] ERROR: neither parquet nor csv created (expected ${OUT_PARQUET} or ${OUT_CSV})" >&2
  exit 1
fi

echo "[train_model_smoke] OK ✅" >&2
