#!/usr/bin/env bash
set -euo pipefail

# scripts/sim_preflight_negative_smoke.sh
#
# PR-5.1 smoke:
# - Run paper_pipeline in deterministic offline mode for negative cases.
# - Verify stdout: exactly one JSON line.
# - Verify sim_metrics: schema_version + skipped_by_reason + TIME fallback.
#
# Success output (stderr, exactly):
#   [sim_preflight_negative] OK ✅

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CFG="integration/fixtures/config/sim_preflight_negative.yaml"

fail() {
  echo "ERROR: sim_preflight_negative_failed: $*" >&2
  exit 1
}

[[ -f "${CFG}" ]] || fail "missing fixture: ${CFG}"

run_case() {
  local name="$1"
  local trades="$2"
  local snap="$3"
  local wprof="$4"

  [[ -f "${trades}" ]] || fail "${name}: missing fixture: ${trades}"
  [[ -f "${snap}" ]] || fail "${name}: missing fixture: ${snap}"
  [[ -f "${wprof}" ]] || fail "${name}: missing fixture: ${wprof}"

  local stdout_tmp
  local stderr_tmp
  stdout_tmp="$(mktemp)"
  stderr_tmp="$(mktemp)"
  trap 'rm -f "${stdout_tmp}" "${stderr_tmp}"' RETURN

  set +e
  python3 -m integration.paper_pipeline \
    --dry-run \
    --summary-json \
    --sim-preflight \
    --config "${CFG}" \
    --trades-jsonl "${trades}" \
    --token-snapshot "${snap}" \
    --wallet-profiles "${wprof}" \
    1>"${stdout_tmp}" 2>"${stderr_tmp}"
  local rc=$?
  set -e

  if [[ ${rc} -ne 0 ]]; then
    echo "ERROR: sim_preflight_negative_failed: ${name}: paper_pipeline exit=${rc}" >&2
    echo "ERROR: sim_preflight_negative_failed: ${name}: stderr follows" >&2
    cat "${stderr_tmp}" >&2
    exit 1
  fi

  local lines
  lines="$(python3 - <<PY
import sys
p = "${stdout_tmp}"
lines = [x for x in open(p, "r", encoding="utf-8").read().splitlines() if x.strip()]
print(len(lines))
PY
)"

  if [[ "${lines}" != "1" ]]; then
    echo "ERROR: sim_preflight_negative_failed: ${name}: expected stdout=1 line, got ${lines}" >&2
    echo "ERROR: sim_preflight_negative_failed: ${name}: stdout follows" >&2
    cat "${stdout_tmp}" >&2
    echo "ERROR: sim_preflight_negative_failed: ${name}: stderr follows" >&2
    cat "${stderr_tmp}" >&2
    exit 1
  fi

  python3 - "${name}" "${stdout_tmp}" <<'PY' 1>/dev/null
import json
import sys

name = sys.argv[1]
p = sys.argv[2]
line = [x for x in open(p, "r", encoding="utf-8").read().splitlines() if x.strip()][0]
try:
    j = json.loads(line)
except Exception:
    print(f"ERROR: sim_preflight_negative_failed: {name}: invalid JSON on stdout", file=sys.stderr)
    sys.exit(1)

sm = j.get("sim_metrics")
if not isinstance(sm, dict):
    print(f"ERROR: sim_preflight_negative_failed: {name}: missing/invalid sim_metrics", file=sys.stderr)
    sys.exit(1)

if sm.get("schema_version") != "sim_metrics.v1":
    print(f"ERROR: sim_preflight_negative_failed: {name}: schema_version mismatch", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

sk = sm.get("skipped_by_reason")
if not isinstance(sk, dict):
    print(f"ERROR: sim_preflight_negative_failed: {name}: missing skipped_by_reason", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

erc = sm.get("exit_reason_counts")
if not isinstance(erc, dict):
    print(f"ERROR: sim_preflight_negative_failed: {name}: missing exit_reason_counts", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

def i(x, default=-1):
    try:
        return int(x)
    except Exception:
        return default

def f(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

pos_closed = i(sm.get("positions_closed"))

def dump_and_fail(msg: str):
    print(f"ERROR: sim_preflight_negative_failed: {name}: {msg}", file=sys.stderr)
    print(json.dumps(sm, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    sys.exit(1)

if name == "missing_snapshot":
    if pos_closed != 0:
        dump_and_fail("positions_closed expected=0")
    if i(sk.get("missing_snapshot")) != 1:
        dump_and_fail("skipped_by_reason.missing_snapshot expected=1")

elif name == "missing_wallet_profile":
    if pos_closed != 0:
        dump_and_fail("positions_closed expected=0")
    if i(sk.get("missing_wallet_profile")) != 1:
        dump_and_fail("skipped_by_reason.missing_wallet_profile expected=1")

elif name == "ev_below_threshold":
    if pos_closed != 0:
        dump_and_fail("positions_closed expected=0")
    if i(sk.get("ev_below_threshold")) != 1:
        dump_and_fail("skipped_by_reason.ev_below_threshold expected=1")

elif name == "no_future_ticks":
    if pos_closed != 1:
        dump_and_fail("positions_closed expected=1")
    if i(erc.get("TIME")) != 1:
        dump_and_fail("exit_reason_counts.TIME expected=1")
    roi = f(sm.get("roi_total"), None)
    avg = f(sm.get("avg_pnl_usd"), None)
    if roi is None or abs(roi) > 1e-12:
        dump_and_fail("roi_total expected=0")
    if avg is None or abs(avg) > 1e-12:
        dump_and_fail("avg_pnl_usd expected=0")

else:
    dump_and_fail(f"unknown case: {name}")

PY
}

# Case matrix
run_case "missing_snapshot" \
  "integration/fixtures/trades.sim_preflight_missing_snapshot.jsonl" \
  "integration/fixtures/token_snapshot.sim_preflight_missing_snapshot.csv" \
  "integration/fixtures/wallet_profiles.sim_preflight.csv"

run_case "missing_wallet_profile" \
  "integration/fixtures/trades.sim_preflight_missing_wallet.jsonl" \
  "integration/fixtures/token_snapshot.sim_preflight.csv" \
  "integration/fixtures/wallet_profiles.sim_preflight_missing_wallet.csv"

run_case "ev_below_threshold" \
  "integration/fixtures/trades.sim_preflight_ev_below_threshold.jsonl" \
  "integration/fixtures/token_snapshot.sim_preflight.csv" \
  "integration/fixtures/wallet_profiles.sim_preflight.csv"

run_case "no_future_ticks" \
  "integration/fixtures/trades.sim_preflight_no_future_ticks.jsonl" \
  "integration/fixtures/token_snapshot.sim_preflight.csv" \
  "integration/fixtures/wallet_profiles.sim_preflight.csv"

# Success token (must be the final line emitted by this script)
echo "[sim_preflight_negative] OK ✅" >&2
