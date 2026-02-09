#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

bash "$ROOT_DIR/scripts/overlay_lint.sh"
echo "[1/4] Smoke (CI == local)"
bash "$ROOT_DIR/scripts/smoke.sh"

echo
echo "[2/4] Generate runtime cfg (strict mapper)"
python3 -m integration.config_mapper

echo
echo "[3/4] Paper runner smoke (JSONL + Parquet, dry-run, import/path sanity)"
bash "$ROOT_DIR/scripts/paper_runner_smoke.sh"

echo
echo "[4/5] Paper pipeline: config_version event (Iteration-1 reproducibility)"
python3 -m integration.paper_pipeline --env canary --config "$ROOT_DIR/strategy/config/params_base.yaml"

echo
echo "[5/5] One-shot exit plan via SQL04 (golden seed)"
python3 -m integration.run_exit_plan --seed-golden
