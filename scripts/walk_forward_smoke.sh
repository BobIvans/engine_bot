#!/usr/bin/env bash
set -euo pipefail

# scripts/walk_forward_smoke.sh
#
# PR-D.1 smoke test:
# - Run walk_forward.py with fixture data
# - Verify output JSON structure
# - Verify sweeps contain window data
#
# Success output (stderr, exactly):
#   [walk_forward_smoke] OK ✅

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CFG="integration/fixtures/config/walk_forward.yaml"
TRADES="integration/fixtures/trades.walk_forward.jsonl"
SNAP="integration/fixtures/token_snapshot.sim_preflight.csv"
WPROF="integration/fixtures/wallet_profiles.sim_preflight.csv"

fail() {
  echo "[walk_forward_smoke] FAIL: $*" >&2
  exit 1
}

[[ -f "${CFG}" ]] || fail "missing fixture: ${CFG}"
[[ -f "${TRADES}" ]] || fail "missing fixture: ${TRADES}"
[[ -f "${SNAP}" ]] || fail "missing fixture: ${SNAP}"
[[ -f "${WPROF}" ]] || fail "missing fixture: ${WPROF}"

OUT_TMP="$(mktemp)"
STDOUT_TMP="$(mktemp)"
STDERR_TMP="$(mktemp)"
cleanup() {
  rm -f "${OUT_TMP}" "${STDOUT_TMP}" "${STDERR_TMP}"
}
trap cleanup EXIT

set +e
python3 -m integration.walk_forward \
  --trades "${TRADES}" \
  --config "${CFG}" \
  --window-days 1 \
  --step-days 1 \
  --token-snapshot "${SNAP}" \
  --wallet-profiles "${WPROF}" \
  --out "${OUT_TMP}" \
  1>"${STDOUT_TMP}" 2>"${STDERR_TMP}"
RC=$?
set -e

if [[ ${RC} -ne 0 ]]; then
  fail "walk_forward exited with code ${RC}, stderr: $(cat "${STDERR_TMP}")"
fi

# Assertion 1: output file exists
if [[ ! -f "${OUT_TMP}" ]]; then
  fail "output file does not exist"
fi

# Assertion 2: file is non-empty
FILE_SIZE="$(stat -f%z "${OUT_TMP}" 2>/dev/null || stat -c%s "${OUT_TMP}" 2>/dev/null || echo "0")"
if [[ "${FILE_SIZE}" == "0" ]]; then
  fail "output file is empty"
fi

# Assertion 3: valid JSON
if ! python3 -c "import json; json.load(open('${OUT_TMP}'))" 2>/dev/null; then
  fail "output file is not valid JSON"
fi

# Assertion 4: schema_version == "results.v1"
SCHEMA_VERSION="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("schema_version", ""))
PY
)"

if [[ "${SCHEMA_VERSION}" != "results.v1" ]]; then
  fail "schema_version=${SCHEMA_VERSION}, expected results.v1"
fi

# Assertion 5: sweeps array exists with at least one entry
SWEEP_COUNT="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
print(len(data.get("sweeps", [])))
PY
)"

if [[ "${SWEEP_COUNT}" == "0" ]]; then
  fail "sweeps array is empty"
fi

# Assertion 6: sweeps[0].name == "walk_forward"
SWEEP_NAME="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("sweeps", [{}])[0].get("name", ""))
PY
)"

if [[ "${SWEEP_NAME}" != "walk_forward" ]]; then
  fail "sweep name=${SWEEP_NAME}, expected walk_forward"
fi

# Assertion 7: sweeps[0].values has 2 dates
VALUES_COUNT="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
vals = data.get("sweeps", [{}])[0].get("values", [])
print(len(vals))
PY
)"

if [[ "${VALUES_COUNT}" != "2" ]]; then
  fail "sweep values count=${VALUES_COUNT}, expected 2"
fi

# Assertion 8: sweeps[0].values contains expected dates (2024-01-01, 2024-01-02)
VALUES_CHECK="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
vals = data.get("sweeps", [{}])[0].get("values", [])
expected = ["2024-01-01", "2024-01-02"]
print(",".join(sorted(vals)) == ",".join(sorted(expected)))
PY
)"

if [[ "${VALUES_CHECK}" != "True" ]]; then
  fail "sweep values do not contain expected dates"
fi

# Assertion 9: sweeps[0].rows has 2 entries (one per window)
ROWS_COUNT="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
rows = data.get("sweeps", [{}])[0].get("rows", [])
print(len(rows))
PY
)"

if [[ "${ROWS_COUNT}" != "2" ]]; then
  fail "sweep rows count=${ROWS_COUNT}, expected 2"
fi

echo "[walk_forward_smoke] OK ✅" >&2
