#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "[smoke] running CANON local smoke (single-path gates)..."
# NOTE: CANON script owns ClickHouse lifecycle (docker compose) and gates:
# - applies DDL
# - asserts no drift
# - canary checks
# - oracle test
#
# We intentionally do NOT start our own ClickHouse here to avoid
# docker-compose conflicts with vendor/gmee_canon/docker-compose.yml.
bash "$ROOT_DIR/vendor/gmee_canon/scripts/local_smoke.sh"

echo "[smoke] OK"
