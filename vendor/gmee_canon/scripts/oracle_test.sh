#!/usr/bin/env bash
set -euo pipefail

# Thin wrapper around the canonical Python gate.
# Keeps local smoke == CI, and avoids sed/curl templating.

python3 ci/oracle_glue_select_gate.py "${1:-ci/oracle_expected.tsv}"

echo "OK: oracle gate passed"
