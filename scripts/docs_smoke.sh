#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DOC_MODES="strategy/docs/overlay/PR_MODES_TUNING.md"
DOC_TIERS="strategy/docs/overlay/PR_WALLET_TIERS.md"
DOC_SIM="strategy/docs/overlay/PR_SIM_PREFLIGHT.md"
DOC_DAILY="strategy/docs/overlay/PR_DAILY_METRICS.md"
DOC_SIGNALS="strategy/docs/overlay/PR_SIGNALS_DUMP.md"
DOC_EXECUTION="strategy/docs/overlay/PR_EXECUTION_PREFLIGHT.md"

# --- PR_MODES_TUNING.md ---
if [[ ! -f "$DOC_MODES" ]]; then
  echo "ERROR: docs_smoke_missing: PR_MODES_TUNING.md" >&2
  exit 1
fi

grep -q "# PR-4A.5: Modes tuning playbook" "$DOC_MODES" || { echo "ERROR: docs_smoke_missing: heading_title" >&2; exit 1; }
grep -q "## Guardrails" "$DOC_MODES" || { echo "ERROR: docs_smoke_missing: heading_guardrails" >&2; exit 1; }
grep -q "## Results template" "$DOC_MODES" || { echo "ERROR: docs_smoke_missing: heading_results_template" >&2; exit 1; }
grep -q "\`__unknown_mode__\`" "$DOC_MODES" || { echo "ERROR: docs_smoke_missing: token___unknown_mode__" >&2; exit 1; }
grep -q "\`__no_mode__\`" "$DOC_MODES" || { echo "ERROR: docs_smoke_missing: token___no_mode__" >&2; exit 1; }

# --- PR_WALLET_TIERS.md ---
if [[ ! -f "$DOC_TIERS" ]]; then
  echo "ERROR: docs_smoke_missing: PR_WALLET_TIERS.md" >&2
  exit 1
fi

grep -q "PR-4B.1" "$DOC_TIERS" || { echo "ERROR: docs_smoke_missing: token_pr4b1" >&2; exit 1; }
grep -q "tier_counts" "$DOC_TIERS" || { echo "ERROR: docs_smoke_missing: token_tier_counts" >&2; exit 1; }
grep -q "\`__missing_wallet_profile__\`" "$DOC_TIERS" || { echo "ERROR: docs_smoke_missing: token___missing_wallet_profile__" >&2; exit 1; }
grep -q "Deterministic tiering rules" "$DOC_TIERS" || { echo "ERROR: docs_smoke_missing: token_deterministic_tiering_rules" >&2; exit 1; }

# --- PR_SIM_PREFLIGHT.md ---
if [[ ! -f "$DOC_SIM" ]]; then
  echo "ERROR: docs_smoke_missing: PR_SIM_PREFLIGHT.md" >&2
  exit 1
fi

grep -q "PR-5" "$DOC_SIM" || { echo "ERROR: docs_smoke_missing: token_pr5" >&2; exit 1; }
grep -q "sim_metrics.v1" "$DOC_SIM" || { echo "ERROR: docs_smoke_missing: token_sim_metrics_v1" >&2; exit 1; }
grep -q "ev_below_threshold" "$DOC_SIM" || { echo "ERROR: docs_smoke_missing: token_ev_below_threshold" >&2; exit 1; }
grep -q "Deterministic preflight" "$DOC_SIM" || { echo "ERROR: docs_smoke_missing: token_deterministic_preflight" >&2; exit 1; }

# --- PR_DAILY_METRICS.md ---
if [[ ! -f "$DOC_DAILY" ]]; then
  echo "ERROR: docs_smoke_missing: PR_DAILY_METRICS.md" >&2
  exit 1
fi

grep -q "PR-7" "$DOC_DAILY" || { echo "ERROR: docs_smoke_missing: token_pr7" >&2; exit 1; }
grep -q "daily_metrics.v1" "$DOC_DAILY" || { echo "ERROR: docs_smoke_missing: token_daily_metrics_v1" >&2; exit 1; }
grep -q "max_drawdown" "$DOC_DAILY" || { echo "ERROR: docs_smoke_missing: token_max_drawdown" >&2; exit 1; }
grep -q "Deterministic daily aggregation" "$DOC_DAILY" || { echo "ERROR: docs_smoke_missing: token_deterministic_daily_aggregation" >&2; exit 1; }

# --- PR_SIGNALS_DUMP.md ---
if [[ ! -f "$DOC_SIGNALS" ]]; then
  echo "ERROR: docs_smoke_missing: PR_SIGNALS_DUMP.md" >&2
  exit 1
fi

grep -q "PR-8.1" "$DOC_SIGNALS" || { echo "ERROR: docs_smoke_missing: token_pr8_1" >&2; exit 1; }
grep -q "signals.v1" "$DOC_SIGNALS" || { echo "ERROR: docs_smoke_missing: token_signals_v1" >&2; exit 1; }
grep -q "reject_reason" "$DOC_SIGNALS" || { echo "ERROR: docs_smoke_missing: token_reject_reason" >&2; exit 1; }
grep -q "DuckDB" "$DOC_SIGNALS" || { echo "ERROR: docs_smoke_missing: token_duckdb" >&2; exit 1; }
grep -q "Deterministic sidecar dump" "$DOC_SIGNALS" || { echo "ERROR: docs_smoke_missing: token_deterministic_sidecar_dump" >&2; exit 1; }


# --- PR_EXECUTION_PREFLIGHT.md ---
if [[ ! -f "$DOC_EXECUTION" ]]; then
  echo "ERROR: docs_smoke_missing: PR_EXECUTION_PREFLIGHT.md" >&2
  exit 1
fi

grep -q "PR-6.1" "$DOC_EXECUTION" || { echo "ERROR: docs_smoke_missing: token_pr6_1" >&2; exit 1; }
grep -q "execution_metrics.v1" "$DOC_EXECUTION" || { echo "ERROR: docs_smoke_missing: token_execution_metrics_v1" >&2; exit 1; }
grep -q "fill_rate" "$DOC_EXECUTION" || { echo "ERROR: docs_smoke_missing: token_fill_rate" >&2; exit 1; }
grep -q "slippage_bps" "$DOC_EXECUTION" || { echo "ERROR: docs_smoke_missing: token_slippage_bps" >&2; exit 1; }
grep -q "Deterministic Execution Model" "$DOC_EXECUTION" || { echo "ERROR: docs_smoke_missing: token_deterministic_execution_model" >&2; exit 1; }


DOC_SHADOW_DIFF="strategy/docs/overlay/PR_SHADOW_DIFF.md"

# --- PR_SHADOW_DIFF.md ---
if [[ ! -f "$DOC_SHADOW_DIFF" ]]; then
  echo "ERROR: docs_smoke_missing: PR_SHADOW_DIFF.md" >&2
  exit 1
fi

grep -q "PR-E.1" "$DOC_SHADOW_DIFF" || { echo "ERROR: docs_smoke_missing: token_pr_e_1" >&2; exit 1; }
grep -q "shadow_diff" "$DOC_SHADOW_DIFF" || { echo "ERROR: docs_smoke_missing: token_shadow_diff" >&2; exit 1; }
grep -q "paper.*live" "$DOC_SHADOW_DIFF" || { echo "ERROR: docs_smoke_missing: token_paper_live" >&2; exit 1; }
grep -q "live.*paper" "$DOC_SHADOW_DIFF" || { echo "ERROR: docs_smoke_missing: token_live_paper" >&2; exit 1; }
grep -q "Deterministic Shadow Diff" "$DOC_SHADOW_DIFF" || { echo "ERROR: docs_smoke_missing: token_deterministic_shadow_diff" >&2; exit 1; }


DOC_EV_SWEEP="strategy/docs/overlay/PR_EV_SWEEP.md"

# --- PR_EV_SWEEP.md ---
if [[ ! -f "$DOC_EV_SWEEP" ]]; then
  echo "ERROR: docs_smoke_missing: PR_EV_SWEEP.md" >&2
  exit 1
fi

grep -q "PR-9" "$DOC_EV_SWEEP" || { echo "ERROR: docs_smoke_missing: token_pr9" >&2; exit 1; }
grep -q "results.v1" "$DOC_EV_SWEEP" || { echo "ERROR: docs_smoke_missing: token_results_v1" >&2; exit 1; }
grep -q "threshold sweep" "$DOC_EV_SWEEP" || { echo "ERROR: docs_smoke_missing: token_threshold_sweep" >&2; exit 1; }
grep -q "min_edge_bps" "$DOC_EV_SWEEP" || { echo "ERROR: docs_smoke_missing: token_min_edge_bps" >&2; exit 1; }
grep -q "Deterministic offline sweep" "$DOC_EV_SWEEP" || { echo "ERROR: docs_smoke_missing: token_deterministic_offline_sweep" >&2; exit 1; }


DOC_RESULTS="strategy/docs/overlay/RESULTS_TEMPLATE.md"
JSON_RESULTS="strategy/docs/overlay/results/results_v1.json"

# --- RESULTS_TEMPLATE.md ---
if [[ ! -f "$DOC_RESULTS" ]]; then
  echo "ERROR: docs_smoke_missing: RESULTS_TEMPLATE.md" >&2
  exit 1
fi

grep -q "RESULTS_TEMPLATE.v1" "$DOC_RESULTS" || { echo "ERROR: docs_smoke_missing: token_RESULTS_TEMPLATE_v1" >&2; exit 1; }
grep -q "Modes summary" "$DOC_RESULTS" || { echo "ERROR: docs_smoke_missing: token_modes_summary" >&2; exit 1; }
grep -q "Wallet tiers summary" "$DOC_RESULTS" || { echo "ERROR: docs_smoke_missing: token_wallet_tiers_summary" >&2; exit 1; }
grep -q "Decision log" "$DOC_RESULTS" || { echo "ERROR: docs_smoke_missing: token_decision_log" >&2; exit 1; }
grep -q "Next parameter changes" "$DOC_RESULTS" || { echo "ERROR: docs_smoke_missing: token_next_parameter_changes" >&2; exit 1; }

# --- results_v1.json (must be valid JSON) ---
if [[ ! -f "$JSON_RESULTS" ]]; then
  echo "ERROR: docs_smoke_missing: results_v1.json" >&2
  exit 1
fi
python3 - <<'PY_JSON' "$JSON_RESULTS"
import json, sys
p = sys.argv[1]
try:
    with open(p, "r", encoding="utf-8") as f:
        json.load(f)
except Exception as e:
    print(f"ERROR: docs_smoke_missing: results_v1_json_invalid", file=sys.stderr)
    raise SystemExit(1)
PY_JSON
echo "[docs_smoke] OK ✅" >&2
