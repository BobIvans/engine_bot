#!/usr/bin/env bash
set -euo pipefail

# scripts/sim_preflight_smoke.sh
#
# PR-5 smoke:
# - Run paper_pipeline with --dry-run --summary-json --sim-preflight
# - Verify stdout: exactly one JSON line
# - Verify sim_metrics: schema_version + expected deterministic exits
#
# Success output (stderr, exactly):
#   [sim_preflight] OK ✅

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CFG="integration/fixtures/config/sim_preflight.yaml"
TRADES="integration/fixtures/trades.sim_preflight.jsonl"
SNAP="integration/fixtures/token_snapshot.sim_preflight.csv"
WPROF="integration/fixtures/wallet_profiles.sim_preflight.csv"
ALLOW="strategy/wallet_allowlist.yaml"

fail() {
  echo "ERROR: sim_preflight_failed: $*" >&2
  exit 1
}

[[ -f "${CFG}" ]] || fail "missing fixture: ${CFG}"
[[ -f "${TRADES}" ]] || fail "missing fixture: ${TRADES}"
[[ -f "${SNAP}" ]] || fail "missing fixture: ${SNAP}"
[[ -f "${WPROF}" ]] || fail "missing fixture: ${WPROF}"
[[ -f "${ALLOW}" ]] || fail "missing allowlist: ${ALLOW}"

STDOUT_TMP="$(mktemp)"
STDERR_TMP="$(mktemp)"
cleanup() {
  rm -f "${STDOUT_TMP}" "${STDERR_TMP}"
}
trap cleanup EXIT

set +e
python3 -m integration.paper_pipeline \
  --dry-run \
  --summary-json \
  --sim-preflight \
  --config "${CFG}" \
  --allowlist "${ALLOW}" \
  --token-snapshot "${SNAP}" \
  --wallet-profiles "${WPROF}" \
  --trades-jsonl "${TRADES}" \
  1>"${STDOUT_TMP}" 2>"${STDERR_TMP}"
RC=$?
set -e

if [[ ${RC} -ne 0 ]]; then
  echo "ERROR: sim_preflight_failed: paper_pipeline exit=${RC}" >&2
  echo "ERROR: sim_preflight_failed: stderr follows" >&2
  cat "${STDERR_TMP}" >&2
  exit 1
fi

# Verify stdout has exactly 1 non-empty line
LINES="$(python3 - <<PY
import sys
p = "${STDOUT_TMP}"
lines = [x for x in open(p, "r", encoding="utf-8").read().splitlines() if x.strip()]
print(len(lines))
PY
)"

if [[ "${LINES}" != "1" ]]; then
  echo "ERROR: sim_preflight_failed: expected stdout=1 line, got ${LINES}" >&2
  echo "ERROR: sim_preflight_failed: stdout follows" >&2
  cat "${STDOUT_TMP}" >&2
  echo "ERROR: sim_preflight_failed: stderr follows" >&2
  cat "${STDERR_TMP}" >&2
  exit 1
fi

# Parse JSON + assert sim_metrics contract
python3 - "${STDOUT_TMP}" <<'PY' 1>/dev/null
import json
import sys

p = sys.argv[1]
line = [x for x in open(p, "r", encoding="utf-8").read().splitlines() if x.strip()][0]
try:
    j = json.loads(line)
except Exception:
    print("ERROR: sim_preflight_failed: invalid JSON on stdout", file=sys.stderr)
    sys.exit(1)

if "sim_metrics" not in j:
    print("ERROR: sim_preflight_failed: missing key sim_metrics", file=sys.stderr)
    sys.exit(1)

sm = j["sim_metrics"]
if not isinstance(sm, dict):
    print("ERROR: sim_preflight_failed: sim_metrics must be object", file=sys.stderr)
    sys.exit(1)

if sm.get("schema_version") != "sim_metrics.v1":
    print("ERROR: sim_preflight_failed: sim_metrics.schema_version mismatch", file=sys.stderr)
    sys.exit(1)

if int(sm.get("positions_closed", -1)) != 2:
    print("ERROR: sim_preflight_failed: positions_closed expected=2", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

erc = sm.get("exit_reason_counts")
if not isinstance(erc, dict):
    print("ERROR: sim_preflight_failed: exit_reason_counts missing/invalid", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

tp = int(erc.get("TP", -1))
sl = int(erc.get("SL", -1))
tm = int(erc.get("TIME", -1))
if tp != 1 or sl != 1 or tm != 0:
    print("ERROR: sim_preflight_failed: exit_reason_counts expected TP=1 SL=1 TIME=0", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)
PY

# Success token (must be the final line emitted by this script)
echo "[sim_preflight] OK ✅" >&2
