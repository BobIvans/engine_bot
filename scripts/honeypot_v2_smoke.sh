#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[honeypot_v2_smoke] ROOT_DIR=${ROOT_DIR}" >&2
echo "[honeypot_v2_smoke] Running honeypot v2 smoke tests..." >&2

# Force imports from this repo only
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"

passed=0
failed=0

run_case () {
  local name="$1"
  local security_json="$2"   # JSON string
  local expect_safe="$3"     # True/False (as string)

  echo -n "[honeypot_v2_smoke] Testing ${name}... " >&2

  if python3 - "$name" "$security_json" "$expect_safe" <<'PY'
import json, sys
from integration.token_snapshot_store import TokenSnapshot
from strategy.honeypot_filter import is_honeypot_safe

name = sys.argv[1]
security_json = sys.argv[2]
expect_safe_s = sys.argv[3].strip()

cfg = {
  "token_profile": {
    "honeypot": {
      "enabled": True,
      "reject_if_freeze_authority_present": True,
      "reject_if_mint_authority_present": True,
    }
  }
}

sec = json.loads(security_json)
snap = TokenSnapshot(mint="TEST", liquidity_usd=1.0, extra={"security": sec})
ok = is_honeypot_safe(snap, cfg)

expected = True if expect_safe_s == "True" else False
assert ok is expected, f"{name}: expected {expected} but got {ok} (sec={sec})"
PY
  then
    echo "PASS" >&2
    passed=$((passed + 1))
  else
    echo "FAIL" >&2
    failed=$((failed + 1))
  fi
}

# JSON can safely use true/false/null because we parse via json.loads
run_case "SOL_GOOD"            '{"is_honeypot": false, "freeze_authority": false, "mint_authority": false, "buy_tax_pct": 0, "sell_tax_pct": 0}'  True
run_case "SCAM_TAX"            '{"is_honeypot": false, "freeze_authority": false, "mint_authority": false, "buy_tax_pct": 99, "sell_tax_pct": 99}' False
run_case "SCAM_HONEY"          '{"is_honeypot": true,  "freeze_authority": false, "mint_authority": false}'                                   False
run_case "SCAM_FREEZE"         '{"is_honeypot": false, "freeze_authority": true,  "mint_authority": false}'                                   False
run_case "SOL_LOW_TAX"         '{"is_honeypot": false, "freeze_authority": false, "mint_authority": false, "buy_tax_pct": 1, "sell_tax_pct": 1}' True
run_case "SOL_UNKNOWN"         '{"is_honeypot": null,  "freeze_authority": null,  "mint_authority": null}'                                    False
run_case "SOL_UNKNOWN_ALLOWED" '{"is_honeypot": null,  "freeze_authority": null,  "mint_authority": null, "allow_unknown": true}'              True

echo "[honeypot_v2_smoke] Results: ${passed} passed, ${failed} failed" >&2

if [[ "${failed}" -ne 0 ]]; then
  echo "[honeypot_v2_smoke] FAIL" >&2
  exit 1
fi

echo "[honeypot_v2_smoke] OK" >&2
