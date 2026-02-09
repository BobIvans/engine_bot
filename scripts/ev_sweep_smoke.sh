#!/usr/bin/env bash
set -euo pipefail

# scripts/ev_sweep_smoke.sh
#
# PR-9 smoke:
# - Run ev_sweep with fixture data
# - Verify stdout is empty (errors go to stderr)
# - Verify output file exists and is valid JSON
# - Verify schema_version == "results.v1"
# - Verify sweeps[0].name == "min_edge_bps"
# - Verify sweeps[0].values == [0,50,100]
# - Verify entered counts: at 0 == 3, at 50 == 2, at 100 == 1
#
# Success output (stderr, exactly):
#   [ev_sweep] OK ✅

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CFG="integration/fixtures/config/ev_sweep.yaml"
TRADES="integration/fixtures/trades.ev_sweep.jsonl"
SNAP="integration/fixtures/token_snapshot.ev_sweep.csv"
WPROF="integration/fixtures/wallet_profiles.ev_sweep.csv"
ALLOW="strategy/wallet_allowlist.yaml"

fail() {
  echo "ERROR: ev_sweep_failed: $*" >&2
  exit 1
}

[[ -f "${CFG}" ]] || fail "missing fixture: ${CFG}"
[[ -f "${TRADES}" ]] || fail "missing fixture: ${TRADES}"
[[ -f "${SNAP}" ]] || fail "missing fixture: ${SNAP}"
[[ -f "${WPROF}" ]] || fail "missing fixture: ${WPROF}"
[[ -f "${ALLOW}" ]] || fail "missing allowlist: ${ALLOW}"

OUT_TMP="$(mktemp)"
STDOUT_TMP="$(mktemp)"
STDERR_TMP="$(mktemp)"
cleanup() {
  rm -f "${OUT_TMP}" "${STDOUT_TMP}" "${STDERR_TMP}"
}
trap cleanup EXIT

set +e
python3 -m integration.ev_sweep \
  --config "${CFG}" \
  --allowlist "${ALLOW}" \
  --token-snapshot "${SNAP}" \
  --wallet-profiles "${WPROF}" \
  --trades-jsonl "${TRADES}" \
  --thresholds-bps "0,50,100" \
  --out "${OUT_TMP}" \
  1>"${STDOUT_TMP}" 2>"${STDERR_TMP}"
RC=$?
set -e

if [[ ${RC} -ne 0 ]]; then
  echo "ERROR: ev_sweep_failed: exit=${RC}" >&2
  echo "ERROR: ev_sweep_failed: stderr follows" >&2
  cat "${STDERR_TMP}" >&2
  exit 1
fi

# Assertion 1: stdout is empty
STDOUT_LINES="$(python3 - <<PY
import sys
p = "${STDOUT_TMP}"
lines = [x for x in open(p, "r", encoding="utf-8").read().splitlines() if x.strip()]
print(len(lines))
PY
)"

if [[ "${STDOUT_LINES}" != "0" ]]; then
  echo "ERROR: ev_sweep_failed: expected stdout empty, got ${STDOUT_LINES} line(s)" >&2
  exit 1
fi

# Assertion 2: file exists and non-empty
if [[ ! -f "${OUT_TMP}" ]]; then
  echo "ERROR: ev_sweep_failed: output file does not exist" >&2
  exit 1
fi

FILE_SIZE="$(stat -f%z "${OUT_TMP}" 2>/dev/null || stat -c%s "${OUT_TMP}" 2>/dev/null || echo "0")"
if [[ "${FILE_SIZE}" == "0" ]]; then
  echo "ERROR: ev_sweep_failed: output file is empty" >&2
  exit 1
fi

# Assertion 3: JSON parses
python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
print("JSON_OK")
PY
if [[ $? -ne 0 ]]; then
  echo "ERROR: ev_sweep_failed: invalid JSON" >&2
  exit 1
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
  echo "ERROR: ev_sweep_failed: schema_version=${SCHEMA_VERSION}, expected results.v1" >&2
  exit 1
fi

# Assertion 5: sweeps[0].name == "min_edge_bps"
SWEEP_NAME="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("sweeps", [{}])[0].get("name", ""))
PY
)"

if [[ "${SWEEP_NAME}" != "min_edge_bps" ]]; then
  echo "ERROR: ev_sweep_failed: sweep_name=${SWEEP_NAME}, expected min_edge_bps" >&2
  exit 1
fi

# Assertion 6: sweeps[0].values == [0,50,100]
SWEEP_VALUES="$(python3 - <<PY
import json
import sys
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
vals = data.get("sweeps", [{}])[0].get("values", [])
print(",".join(str(v) for v in vals))
PY
)"

if [[ "${SWEEP_VALUES}" != "0,50,100" ]]; then
  echo "ERROR: ev_sweep_failed: sweep_values=${SWEEP_VALUES}, expected 0,50,100" >&2
  exit 1
fi

# Assertion 7: entered counts: at 0 == 3, at 50 == 2, at 100 == 1
ENTERED_0="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
rows = data.get("sweeps", [{}])[0].get("rows", [])
for r in rows:
    if r.get("value") == 0:
        print(r.get("sim_metrics", {}).get("positions_total", 0))
        break
PY
)"

ENTERED_50="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
rows = data.get("sweeps", [{}])[0].get("rows", [])
for r in rows:
    if r.get("value") == 50:
        print(r.get("sim_metrics", {}).get("positions_total", 0))
        break
PY
)"

ENTERED_100="$(python3 - <<PY
import json
with open("${OUT_TMP}", "r", encoding="utf-8") as f:
    data = json.load(f)
rows = data.get("sweeps", [{}])[0].get("rows", [])
for r in rows:
    if r.get("value") == 100:
        print(r.get("sim_metrics", {}).get("positions_total", 0))
        break
PY
)"

if [[ "${ENTERED_0}" != "3" ]]; then
  echo "ERROR: ev_sweep_failed: entered at 0=${ENTERED_0}, expected 3" >&2
  exit 1
fi

if [[ "${ENTERED_50}" != "2" ]]; then
  echo "ERROR: ev_sweep_failed: entered at 50=${ENTERED_50}, expected 2" >&2
  exit 1
fi

if [[ "${ENTERED_100}" != "1" ]]; then
  echo "ERROR: ev_sweep_failed: entered at 100=${ENTERED_100}, expected 1" >&2
  exit 1
fi

echo "[ev_sweep] OK ✅" >&2
