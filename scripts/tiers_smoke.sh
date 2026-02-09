#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG="strategy/config/params_base.yaml"
ALLOWLIST="strategy/wallet_allowlist.yaml"
SNAP="integration/fixtures/token_snapshot.sample.csv"

TIERS_WP="integration/fixtures/wallet_profiles.tiers_two_profiles.sample.csv"
TIERS_TRADES="integration/fixtures/trades.tiers_two_profiles.jsonl"

out_file="/tmp/tiers_smoke.out"
err_file="/tmp/tiers_smoke.err"
rm -f "$out_file" "$err_file"

dump_tier_counts_from_out() {
  # Best-effort: if stdout has a JSON summary line, print tier_counts for debugging.
  if [[ ! -s "$out_file" ]]; then
    return 0
  fi
  python3 - "$out_file" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
lines = [ln.strip() for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]
if not lines:
    raise SystemExit(0)
try:
    j = json.loads(lines[0])
except Exception:
    raise SystemExit(0)
print("tier_counts_dump=" + json.dumps(j.get("tier_counts"), ensure_ascii=False, sort_keys=True, indent=2), file=sys.stderr)
print("counts_dump=" + json.dumps(j.get("counts"), ensure_ascii=False, sort_keys=True, indent=2), file=sys.stderr)
PY
PY_STATUS=$?
if [[ "$PY_STATUS" -ne 0 ]]; then
  echo "ERROR: tiers_smoke_failed: summary json parse/shape check failed" >&2
  dump_tier_counts_from_out
  exit 1
fi
}

rc=0
python3 -m integration.paper_pipeline --dry-run --summary-json \
  --config "$CONFIG" \
  --allowlist "$ALLOWLIST" \
  --token-snapshot "$SNAP" \
  --wallet-profiles "$TIERS_WP" \
  --trades-jsonl "$TIERS_TRADES" \
  1>"$out_file" 2>"$err_file" || rc=$?

if [[ "$rc" -ne 0 ]]; then
  echo "ERROR: tiers_smoke_failed: paper_pipeline exited non-zero: $rc" >&2
  if [[ -s "$err_file" ]]; then
    echo "stderr_dump=" >&2
    cat "$err_file" >&2
  fi
  dump_tier_counts_from_out
  exit 1
fi

# stdout must be exactly 1 non-empty line
LINES=$(grep -c . "$out_file" || true)
if [[ "$LINES" -ne 1 ]]; then
  echo "ERROR: tiers_smoke_failed: expected stdout=1 line, got $LINES" >&2
  if [[ -s "$out_file" ]]; then
    echo "stdout_dump=" >&2
    cat "$out_file" >&2
  fi
  if [[ -s "$err_file" ]]; then
    echo "stderr_dump=" >&2
    cat "$err_file" >&2
  fi
  dump_tier_counts_from_out
  exit 1
fi

set +e
python3 - "$out_file" <<'PY'
import json, sys
from pathlib import Path
j = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if "counts" not in j:
    raise SystemExit("missing counts")
if "tier_counts" not in j:
    raise SystemExit("missing tier_counts")

counts = j["counts"]
tiers = j["tier_counts"]

for t in ("tier1", "tier3"):
    if t not in tiers:
        raise SystemExit(f"missing tier bucket {t}")
    if int(tiers[t].get("total_lines", 0)) != 1:
        raise SystemExit(f"{t}.total_lines != 1")

total_lines_counts = int(counts.get("total_lines", -1))
sum_tier_total = sum(int(v.get("total_lines", 0)) for v in tiers.values())
if total_lines_counts != 2:
    raise SystemExit(f"counts.total_lines != 2 (got {total_lines_counts})")
if sum_tier_total != total_lines_counts:
    raise SystemExit(f"sum(tier_counts.total_lines)={sum_tier_total} != counts.total_lines={total_lines_counts}")
PY
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "ERROR: tiers_smoke_failed: summary json parse/shape check failed" >&2
  dump_tier_counts_from_out
  exit 1
fi


echo "[tiers_smoke] OK ✅" >&2
