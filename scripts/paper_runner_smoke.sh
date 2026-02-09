#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Guardrail: validate strategy config before running the pipeline.
bash scripts/config_smoke.sh

function _run_pipeline_summary_json() {
  local name="$1"; shift
  echo "[paper_runner_smoke] ${name} ..." >&2
  local tmp_out
  tmp_out="$(mktemp)"
  # Ensure temp file is always removed even if validation fails.
  trap 'rm -f "$tmp_out"' RETURN

  # Capture stdout into a file; pass stderr through unchanged.
  # Contract: when --summary-json is used, stdout MUST be exactly one JSON line.
  "$@" >"$tmp_out" 2> >(cat >&2)

  # Validate stdout is exactly 1 non-empty line and is valid JSON.
  python3 - "$tmp_out" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

# Drop leading/trailing empty lines (shouldn't exist, but keep error messages clean).
while lines and lines[0].strip() == "":
    lines.pop(0)
while lines and lines[-1].strip() == "":
    lines.pop()

if len(lines) != 1:
    sys.stderr.write("[paper_runner_smoke] FAIL: --summary-json stdout must be exactly 1 JSON line\n")
    sys.stderr.write(f"  got_lines={len(lines)}\n")
    sys.stderr.write("  stdout_dump:\n")
    for i, ln in enumerate(lines, 1):
        sys.stderr.write(f"    {i:02d}: {ln}\n")
    raise SystemExit(1)

line = lines[0]
try:
    obj = json.loads(line)
except Exception as e:
    sys.stderr.write("[paper_runner_smoke] FAIL: --summary-json stdout is not valid JSON\n")
    sys.stderr.write(f"  error={type(e).__name__}: {e}\n")
    sys.stderr.write(f"  line={line!r}\n")
    raise SystemExit(1)

if not isinstance(obj, dict):
    sys.stderr.write("[paper_runner_smoke] FAIL: --summary-json must be a JSON object\n")
    sys.stderr.write(f"  got_type={type(obj).__name__}\n")
    raise SystemExit(1)

print(line)
PY

  # tmp_out cleaned by RETURN trap
}

function _assert_counts() {
  local case_name="$1" summary_json_line="$2" expected_file="$3"
  python3 - "$case_name" "$summary_json_line" "$expected_file" <<'PY'
import json, sys
case_name = sys.argv[1]
summary = json.loads(sys.argv[2])
expected = json.load(open(sys.argv[3], 'r', encoding='utf-8'))
exp = expected['cases'][case_name]['expected_counts']
got = summary.get('counts', {})
missing = []
mismatch = []
for k, v in exp.items():
    if k not in got:
        missing.append(k)
    elif got[k] != v:
        mismatch.append((k, v, got[k]))
if missing or mismatch:
    print(f"[paper_runner_smoke] ASSERT FAIL case={case_name}", file=sys.stderr)
    if missing:
        print(f"  missing_keys={missing}", file=sys.stderr)
    for k, e, g in mismatch:
        print(f"  {k}: expected={e} got={g}", file=sys.stderr)
    print("  summary=...", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)
PY
}

echo "[paper_runner_smoke] generating deterministic parquet fixture (no binary in repo)..." >&2
OUT_PARQUET="${OUT_PARQUET:-/tmp/trades.sample.parquet}"

HAVE_DUCKDB=1
if ! python3 - <<'PY'
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('duckdb') is not None else 1)
PY
then
  HAVE_DUCKDB=0
  echo "[paper_runner_smoke] WARN: duckdb not available -> skipping parquet smoke" >&2
else
  python3 -m integration.make_parquet_fixture \
    --input-csv integration/fixtures/trades.sample.csv \
    --output-parquet "$OUT_PARQUET"
fi

echo "[paper_runner_smoke] validating JSONL fixture schema (trade_v1)..." >&2
# Single source of truth: integration/trade_schema.json + dependency-free validator.
python3 -m integration.validate_trade_jsonl_json \
  --schema integration/trade_schema.json \
  --jsonl integration/fixtures/trades.sample.jsonl

EXPECTED_FILE="integration/fixtures/expected_counts.json"

summary_json="$(_run_pipeline_summary_json "JSONL sample (dry-run)" python3 -m integration.paper_pipeline \
  --dry-run \
  --summary-json \
  --trades-jsonl integration/fixtures/trades.sample.jsonl \
  --token-snapshot integration/fixtures/token_snapshot.sample.csv \
  --only-buy)"
_assert_counts "sample_jsonl" "$summary_json" "$EXPECTED_FILE"

if [[ "$HAVE_DUCKDB" -eq 1 ]]; then
  summary_json="$(_run_pipeline_summary_json "Parquet sample (dry-run)" python3 -m integration.paper_pipeline \
    --dry-run \
    --summary-json \
    --trades-parquet "$OUT_PARQUET" \
    --token-snapshot integration/fixtures/token_snapshot.sample.csv \
    --only-buy)"
  _assert_counts "parquet_sample" "$summary_json" "$EXPECTED_FILE"
fi

summary_json="$(_run_pipeline_summary_json "Edgecases JSONL (dry-run)" python3 -m integration.paper_pipeline \
  --dry-run \
  --summary-json \
  --trades-jsonl integration/fixtures/trades.edgecases.jsonl \
  --token-snapshot integration/fixtures/token_snapshot.sample.csv \
  --only-buy)"
_assert_counts "edgecases_jsonl" "$summary_json" "$EXPECTED_FILE"

echo "[paper_runner_smoke] OK ✅"
