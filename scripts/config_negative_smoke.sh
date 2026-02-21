#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run_case() {
  local cfg="$1"
  local expect_substr="$2"

  local stdout_file stderr_file
  stdout_file="${TMPDIR:-/tmp}/cfgneg.stdout.$$.$(basename "$cfg")"
  stderr_file="${TMPDIR:-/tmp}/cfgneg.stderr.$$.$(basename "$cfg")"

  set +e
  python3 -m integration.validate_strategy_config --config "$cfg" 1>"$stdout_file" 2>"$stderr_file"
  local rc=$?
  set -e

  if [[ $rc -ne 2 ]]; then
    echo "ERROR: expected exit code 2 for $cfg, got $rc" >&2
    echo "--- stderr ---" >&2
    sed -n '1,200p' "$stderr_file" >&2 || true
    echo "--- stdout ---" >&2
    sed -n '1,200p' "$stdout_file" >&2 || true
    rm -f "$stdout_file" "$stderr_file" || true
    exit 1
  fi

  if [[ -s "$stdout_file" ]]; then
    echo "ERROR: expected empty stdout for $cfg" >&2
    echo "--- stdout ---" >&2
    sed -n '1,200p' "$stdout_file" >&2 || true
    rm -f "$stdout_file" "$stderr_file" || true
    exit 1
  fi

  if ! grep -Fq "$expect_substr" "$stderr_file"; then
    echo "ERROR: expected stderr to contain: $expect_substr" >&2
    echo "ERROR: stderr did not match for $cfg" >&2
    echo "--- stderr ---" >&2
    sed -n '1,200p' "$stderr_file" >&2 || true
    rm -f "$stdout_file" "$stderr_file" || true
    exit 1
  fi

  rm -f "$stdout_file" "$stderr_file" || true
}

run_case "integration/fixtures/config/bad_ttl_sec.yaml" "ERROR: mode 'X': ttl_sec must be an integer > 0"
run_case "integration/fixtures/config/bad_tp_pct.yaml" "ERROR: mode 'X': tp_pct must be a number > 0"
run_case "integration/fixtures/config/bad_sl_pct.yaml" "ERROR: mode 'X': sl_pct must be a number < 0"
run_case "integration/fixtures/config/bad_hold_sec_order.yaml" "ERROR: mode 'X': hold_sec_max must be >= hold_sec_min"
