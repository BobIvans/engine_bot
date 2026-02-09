#!/usr/bin/env bash
set -euo pipefail

# Local smoke runner (requires docker + docker compose)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

# 1) Start ClickHouse
if [ -f docker-compose.yml ]; then
  docker compose up -d
else
  echo "docker-compose.yml not found" >&2
  exit 1
fi

# 2) Wait for CH
for i in {1..60}; do
  if curl -sSf http://localhost:8123/ping >/dev/null; then
    echo "ClickHouse is up"
    break
  fi
  sleep 1
done

# 3) Apply DDL
docker exec -i clickhouse clickhouse-client --multiquery < schemas/clickhouse.sql

# 4) Anti-drift gate
python3 -m pip -q install pyyaml >/dev/null
python3 scripts/assert_no_drift.py

# 5) Canary
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_golden_trace.sql
docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_checks.sql

# 6) Oracle
bash scripts/oracle_test.sh

echo "[OK] local_smoke" 
