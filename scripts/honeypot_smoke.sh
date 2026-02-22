#!/usr/bin/env bash
# scripts/honeypot_smoke.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[honeypot_smoke] ROOT_DIR=${ROOT_DIR}" >&2
echo "[honeypot_smoke] Starting honeypot filter smoke test..." >&2

cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

python3 - <<'PY'
import sys
from strategy.honeypot_filter import check_security
from integration.token_snapshot_store import TokenSnapshot
from integration.reject_reasons import HONEYPOT_FLAG, HONEYPOT_FREEZE, HONEYPOT_MINT_AUTH

passed = 0
failed = 0

def test_case(name, expected_pass, expected_reason, snapshot, cfg):
    global passed, failed
    got_pass, got_reason = check_security(snapshot, cfg)
    if got_pass == expected_pass and got_reason == expected_reason:
        print(f"  [honeypot] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(
            f"  [honeypot] {name}: FAIL (got pass={got_pass}, reason={got_reason}, "
            f"expected pass={expected_pass}, reason={expected_reason})",
            file=sys.stderr,
        )
        failed += 1

print("[honeypot_smoke] Running pure logic tests...", file=sys.stderr)

cfg_enabled = {"token_profile": {"honeypot": {"enabled": True}}}
cfg_enabled_freeze = {"token_profile": {"honeypot": {"enabled": True, "reject_if_freeze_authority_present": True}}}
cfg_enabled_mint = {"token_profile": {"honeypot": {"enabled": True, "reject_if_mint_authority_present": True}}}

good_security = {"is_honeypot": False, "freeze_authority": False, "mint_authority": False}
good_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    extra={"security": good_security},
)
test_case("good_token_passes", True, None, good_snapshot, cfg_enabled)

honeypot_security = {"is_honeypot": True, "freeze_authority": False, "mint_authority": False}
honeypot_snapshot = TokenSnapshot(
    mint="4STG2XSPty6j9u66oK7ptFfFkSbg7Y2K3i4Eq3S4c7qF",
    liquidity_usd=30000.0,
    extra={"security": honeypot_security},
)
test_case("honeypot_token_rejected", False, HONEYPOT_FLAG, honeypot_snapshot, cfg_enabled)

freeze_security = {"is_honeypot": False, "freeze_authority": True, "mint_authority": False}
freeze_snapshot = TokenSnapshot(
    mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPBzk",
    liquidity_usd=25000.0,
    extra={"security": freeze_security},
)
test_case("freeze_authority_rejected", False, HONEYPOT_FREEZE, freeze_snapshot, cfg_enabled_freeze)

mint_security = {"is_honeypot": False, "freeze_authority": False, "mint_authority": True}
mint_snapshot = TokenSnapshot(
    mint="7nYhPEPDysnfwadnJq3Tz4Q4j3G9J8XZJYJDDqyMDr3Y",
    liquidity_usd=40000.0,
    extra={"security": mint_security},
)
test_case("mint_authority_rejected", False, HONEYPOT_MINT_AUTH, mint_snapshot, cfg_enabled_mint)

# SoT aligned with security_gate_smoke:
# - null snapshot should pass
test_case("null_snapshot_passes", True, None, None, cfg_enabled)

# - no security data should pass
no_security_snapshot = TokenSnapshot(
    mint="So11111111111111111111111111111111111111112",
    liquidity_usd=50000.0,
    extra={},  # no "security"
)
test_case("no_security_data_passes", True, None, no_security_snapshot, cfg_enabled)

print(f"\n[honeypot_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)
if failed:
    sys.exit(1)

print("[honeypot_smoke] OK ✅", file=sys.stderr)
PY

echo "[honeypot_smoke] Smoke test completed." >&2
