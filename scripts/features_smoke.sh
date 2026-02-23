#!/usr/bin/env bash
set -euo pipefail

TMP_OUT="${TMPDIR:-/tmp}/dataset.sample.parquet"
LABEL_HORIZON_SEC=300
COV_JSON="${TMPDIR:-/tmp}/coverage.sample.json"
COV_ERR="${TMPDIR:-/tmp}/coverage.sample.stderr"

rm -f "$COV_JSON" "$COV_ERR"

echo "[features_smoke] exporting dataset to ${TMP_OUT}" >&2
# Capture exporter stderr so we can validate the COVERAGE line.
(
  python3 tools/export_training_dataset.py \
    --trades-jsonl integration/fixtures/trades.sample.jsonl \
    --token-snapshot integration/fixtures/token_snapshot.sample.csv \
    --wallet-profiles integration/fixtures/wallet_profiles.sample.csv \
    --label-horizon-sec "${LABEL_HORIZON_SEC}" \
    --coverage-out "$COV_JSON" \
    --coverage-stderr \
    --out-parquet "${TMP_OUT}" \
    1>/dev/null
) 2>"$COV_ERR"

if [[ ! -s "$COV_JSON" ]]; then
  echo "ERROR: coverage-out file missing: $COV_JSON" >&2
  exit 1
fi
if [[ $(grep -c '^COVERAGE: ' "$COV_ERR" || true) -ne 1 ]]; then
  echo "ERROR: missing COVERAGE line in stderr" >&2
  sed -n '1,50p' "$COV_ERR" >&2 || true
  exit 1
fi

echo "[features_smoke] verifying f_* feature keys" >&2
DATASET_PATH="$TMP_OUT" COV_PATH="$COV_JSON" LABEL_HORIZON_SEC="$LABEL_HORIZON_SEC" python3 - <<'PY'
import csv
import json
import os
from pathlib import Path

expected = json.loads(Path("integration/fixtures/features_expected.json").read_text(encoding="utf-8"))
want = sorted(expected.get("feature_keys", []))
if not want:
    raise SystemExit("features_expected.json missing feature_keys")

out = Path(os.environ["DATASET_PATH"])

def read_columns(path: Path) -> list[str]:
    # Prefer parquet if duckdb is available; otherwise use csv.
    if path.suffix == ".parquet":
        try:
            import duckdb  # type: ignore
        except Exception:
            # Fallback: exporter may have written CSV next to parquet.
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                path = csv_path
            else:
                raise SystemExit("duckdb not available and CSV fallback not found")
        else:
            con = duckdb.connect()
            cols = [r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{path.as_posix()}')"
            ).fetchall()]
            return cols

    # CSV path
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            raise SystemExit("dataset CSV is empty")
        return header

cols = read_columns(out)
have = sorted([c for c in cols if c.startswith("f_")])
if have != want:
    raise SystemExit(
        "Feature key mismatch\n" + f"expected={want}\n" + f"have={have}\n"
    )
print("OK: feature keys match")

# Coverage contract checks
cov = json.loads(Path(os.environ["COV_PATH"]).read_text(encoding="utf-8"))
if cov.get("schema_version") != "coverage.v1":
    raise SystemExit("ERROR: coverage schema_version mismatch")
rows_written = int(cov.get("rows_written", 0))
if rows_written <= 0:
    raise SystemExit("ERROR: coverage rows_written must be > 0")
if int(cov.get("label_horizon_sec", -1)) != int(os.environ["LABEL_HORIZON_SEC"]):
    raise SystemExit("ERROR: coverage label_horizon_sec mismatch")
labels = cov.get("labels", {})
if labels.get("y_horizon_sec", {}).get("null") != 0:
    raise SystemExit("ERROR: coverage expected y_horizon_sec.null == 0")
print("OK: coverage checks")
PY

echo "[features_smoke] OK" >&2
