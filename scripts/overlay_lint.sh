#!/bin/bash
# scripts/overlay_lint.sh
# Master lint and smoke test runner

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() {
  echo -e "${RED}[overlay_lint] FAIL: $*${NC}" >&2
  exit 1
}

pass() {
  echo -e "${GREEN}[overlay_lint] PASS: $*${NC}" >&2
}

# Helper: list matches excluding vendor/*
# Using 'find' with -print0 for safety.
find_outside_vendor() {
  local pattern="$1"
  (cd "${ROOT_DIR}" && find . -path './vendor/*' -prune -o -name "$pattern" -print)
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[overlay_lint] Starting overlay lint checks..." >&2

# 1) No golden-engine-exit directories outside vendor/
golden_hits="$(find_outside_vendor 'golden-engine-exit')"
if [[ -n "$golden_hits" ]]; then
  fail "Found golden-engine-exit directory outside vendor/. Overlay must be docs-only."
fi
pass "no golden-engine-exit outside vendor"

# 2) No SQL/DDL outside vendor
sql_hits="$(find_outside_vendor '*.sql')"
ddl_hits="$(find_outside_vendor '*.ddl')"
if [[ -n "$sql_hits" || -n "$ddl_hits" ]]; then
  fail "Found *.sql/*.ddl outside vendor/. SQL/DDL must live only in vendor/gmee_canon (CANON)."
fi
pass "no *.sql/*.ddl outside vendor"

# 3) Overlay directories only under strategy/docs
# Use find with -print0 and read with null delimiter to handle spaces in paths
while IFS= read -r -d '' d; do
  if [[ "$d" != "$ROOT_DIR/strategy/docs/overlay" ]]; then
    fail "Unexpected overlay directory location: $d. Expected only strategy/docs/overlay."
  fi
done < <(find "$ROOT_DIR/strategy" -type d -name 'overlay' -print0 2>/dev/null || true)
pass "overlay directory location OK"

# 4) No confusing legacy paths in overlay
legacy_refs=$(grep -r "golden-engine-exit" "$ROOT_DIR/strategy/docs" --include="*.md" -n 2>/dev/null || true)
if [[ -n "$legacy_refs" ]]; then
  bad_refs=$(echo "$legacy_refs" | grep -v "LEGACY_PATH:" || true)
  if [[ -n "$bad_refs" ]]; then
    fail "Overlay references legacy path golden-engine-exit without LEGACY_PATH banner."
  fi
fi
pass "no confusing legacy paths in overlay"

# Run smoke tests
echo "[overlay_lint] linting PR labels (SoT vs docs)" >&2

echo "[overlay_lint] running modes smoke..." >&2
bash scripts/modes_smoke.sh

echo "[overlay_lint] running tiers smoke..." >&2
bash scripts/tiers_smoke.sh

echo "[overlay_lint] running token state smoke..." >&2
bash scripts/token_state_smoke.sh

echo "[overlay_lint] running signal engine smoke..." >&2
bash scripts/signal_engine_smoke.sh

echo "[overlay_lint] running sim preflight smoke..." >&2
bash scripts/sim_preflight_smoke.sh

echo "[overlay_lint] running sim preflight negative smoke..." >&2
bash scripts/sim_preflight_negative_smoke.sh

echo "[overlay_lint] running daily metrics smoke..." >&2
bash scripts/daily_metrics_smoke.sh

echo "[overlay_lint] running daily metrics negative smoke..." >&2
bash scripts/daily_metrics_negative_smoke.sh

echo "[overlay_lint] running signals dump smoke..." >&2
bash scripts/signals_dump_smoke.sh

echo "[overlay_lint] running execution preflight smoke..." >&2
bash scripts/execution_preflight_smoke.sh

echo "[overlay_lint] running wallet profiler smoke..." >&2
bash scripts/wallet_profiler_smoke.sh

echo "[overlay_lint] running walk forward smoke..." >&2
bash scripts/walk_forward_smoke.sh

echo "[overlay_lint] running shadow diff smoke..." >&2
bash scripts/shadow_diff_smoke.sh

echo "[overlay_lint] running live ingestion smoke..." >&2
bash scripts/live_ingestion_smoke.sh

echo "[overlay_lint] running live snapshot smoke..." >&2
bash scripts/live_snapshot_smoke.sh

echo "[overlay_lint] running ev sweep smoke..." >&2
bash scripts/ev_sweep_smoke.sh

echo "[overlay_lint] running risk engine smoke..." >&2
bash scripts/risk_engine_smoke.sh

echo "[overlay_lint] running risk cooldown smoke..." >&2
bash scripts/risk_cooldown_smoke.sh

echo "[overlay_lint] running risk wallet tier smoke..." >&2
bash scripts/risk_wallet_tier_smoke.sh

echo "[overlay_lint] running risk mode smoke..." >&2
bash scripts/risk_mode_smoke.sh

echo "[overlay_lint] running security gate smoke..." >&2
bash scripts/security_gate_smoke.sh

echo "[overlay_lint] running honeypot smoke..." >&2
bash scripts/honeypot_smoke.sh

echo "[overlay_lint] running honeypot v2 smoke..." >&2
bash scripts/honeypot_v2_smoke.sh

echo "[overlay_lint] running honeypot gate smoke..." >&2
bash scripts/honeypot_gate_smoke.sh

echo "[overlay_lint] running survival analysis smoke..." >&2
bash scripts/survival_smoke.sh

echo "[overlay_lint] running decision smoke..." >&2
bash scripts/decision_smoke.sh

echo "[overlay_lint] running aggr switch smoke..." >&2
bash scripts/aggr_switch_smoke.sh

echo "[overlay_lint] running mode selector smoke..." >&2
bash scripts/mode_selector_smoke.sh

echo "[overlay_lint] running risk v2 smoke..." >&2
bash scripts/risk_v2_smoke.sh

echo "[overlay_lint] running features v2 smoke..." >&2
bash scripts/features_v2_smoke.sh

echo "[overlay_lint] running train model smoke..." >&2
bash scripts/train_model_smoke.sh

echo "[overlay_lint] running inference smoke..." >&2
bash scripts/inference_smoke.sh

echo "[overlay_lint] running realtime smoke..." >&2
bash scripts/realtime_smoke.sh

echo "[overlay_lint] running queues smoke..." >&2
bash scripts/queues_smoke.sh

echo "[overlay_lint] running alerts smoke..." >&2
bash scripts/alerts_smoke.sh

echo "[overlay_lint] running dynamic exec smoke..." >&2
bash scripts/dynamic_exec_smoke.sh

echo "[overlay_lint] running tuning smoke..." >&2
bash scripts/tuning_smoke.sh

echo "[overlay_lint] running polymarket smoke..." >&2
bash scripts/polymarket_smoke.sh

echo "[overlay_lint] running sentiment smoke..." >&2
bash scripts/sentiment_smoke.sh

echo "[overlay_lint] running token_mapping smoke..." >&2
bash scripts/token_mapping_smoke.sh

echo "[overlay_lint] running live exec smoke..." >&2
bash scripts/live_exec_smoke.sh

echo "[overlay_lint] running key gate smoke..." >&2
bash scripts/key_gate_smoke.sh

echo "[overlay_lint] running discovery smoke..." >&2
bash scripts/discovery_smoke.sh

echo "[overlay_lint] running promotion smoke..." >&2
bash scripts/promotion_smoke.sh

echo "[overlay_lint] running data track smoke..." >&2
bash scripts/data_track_smoke.sh

echo "[overlay_lint] running calibration smoke..." >&2
bash scripts/calibration_smoke.sh

echo "[overlay_lint] running ml trigger smoke..." >&2
bash scripts/ml_trigger_smoke.sh

echo "[overlay_lint] running amm smoke..." >&2
bash scripts/amm_smoke.sh

echo "[overlay_lint] running jito smoke..." >&2
bash scripts/jito_smoke.sh

echo "[overlay_lint] running monte carlo smoke..." >&2
bash scripts/monte_carlo_smoke.sh

echo "[overlay_lint] running grafana export smoke..." >&2
bash scripts/grafana_export_smoke.sh

echo "[overlay_lint] running exits smoke..." >&2
bash scripts/exits_smoke.sh

echo "[overlay_lint] running polymarket smoke..." >&2
bash scripts/polymarket_smoke.sh

echo "[overlay_lint] running slippage smoke..." >&2
bash scripts/slippage_smoke.sh

echo "[overlay_lint] running risk aggr smoke..." >&2
bash scripts/risk_aggr_smoke.sh

echo "[overlay_lint] running smart money smoke..." >&2
bash scripts/smart_money_smoke.sh

echo "[overlay_lint] running features wiring smoke..." >&2
bash scripts/features_wiring_smoke.sh

echo "[overlay_lint] running state smoke..." >&2
bash scripts/state_smoke.sh

echo "[overlay_lint] running latency smoke..." >&2
bash scripts/latency_smoke.sh

echo "[overlay_lint] running feedback loop smoke..." >&2
bash scripts/feedback_loop_smoke.sh

echo "[overlay_lint] running calibration adapter smoke..." >&2
bash scripts/calibration_adapter_smoke.sh

echo "[overlay_lint] running panic smoke..." >&2
bash scripts/panic_smoke.sh

echo "[overlay_lint] running order manager smoke..." >&2
bash scripts/order_manager_smoke.sh

echo "[overlay_lint] running promotion smoke..." >&2
bash scripts/promotion_smoke.sh

echo "[overlay_lint] running state reconciler smoke..." >&2
bash scripts/state_reconciler_smoke.sh

echo "[overlay_lint] running jito bundle smoke..." >&2
bash scripts/jito_bundle_smoke.sh

echo "[overlay_lint] running update params smoke..." >&2
bash scripts/update_params_smoke.sh

echo "[overlay_lint] running rpc smoke..." >&2
bash scripts/rpc_smoke.sh

echo "[overlay_lint] running rpc failover smoke..." >&2
bash scripts/rpc_failover_smoke.sh

echo "[overlay_lint] running pyth smoke..." >&2
bash scripts/pyth_smoke.sh

echo "[overlay_lint] running das smoke..." >&2
bash scripts/das_smoke.sh

echo "[overlay_lint] running jupiter smoke..." >&2
bash scripts/jupiter_smoke.sh

echo "[overlay_lint] running raydium smoke..." >&2
bash scripts/raydium_smoke.sh

echo "[overlay_lint] running orca smoke..." >&2
bash scripts/orca_smoke.sh

echo "[overlay_lint] running meteora smoke..." >&2
bash scripts/meteora_smoke.sh

echo "[overlay_lint] running router smoke..." >&2
bash scripts/router_smoke.sh

echo "[overlay_lint] running micro live smoke..." >&2
bash scripts/micro_live_smoke.sh

echo "[overlay_lint] running clustering ml smoke..." >&2
bash scripts/clustering_ml_smoke.sh

echo "[overlay_lint] running sweep smoke..." >&2
bash scripts/sweep_smoke.sh

echo "[overlay_lint] running allocation smoke..." >&2
bash scripts/allocation_smoke.sh

echo "[overlay_lint] running timing analysis smoke..." >&2
bash scripts/timing_analysis_smoke.sh

echo "[overlay_lint] running feature drift smoke..." >&2
bash scripts/feature_drift_smoke.sh

echo "[overlay_lint] running token22 smoke..." >&2
bash scripts/token22_smoke.sh

echo "[overlay_lint] running rugcheck smoke..." >&2
bash scripts/rugcheck_smoke.sh

echo "[overlay_lint] running resource monitor smoke..." >&2
bash scripts/resource_monitor_smoke.sh

echo "[overlay_lint] running attribution smoke..." >&2
bash scripts/attribution_smoke.sh

echo "[overlay_lint] running tier autoscaling smoke..." >&2
bash scripts/tier_autoscaling_smoke.sh

echo "[overlay_lint] running forensics smoke..." >&2
bash scripts/forensics_smoke.sh

echo "[overlay_lint] running parallel backtest smoke..." >&2
bash scripts/parallel_backtest_smoke.sh

echo "[overlay_lint] running bitquery smoke..." >&2
bash scripts/bitquery_smoke.sh

echo "[overlay_lint] running flipside smoke..." >&2
bash scripts/flipside_smoke.sh

echo "[overlay_lint] running kolscan smoke..." >&2
bash scripts/kolscan_smoke.sh

echo "[overlay_lint] running trailing dynamic smoke..." >&2
bash scripts/trailing_dynamic_smoke.sh

echo "[overlay_lint] running dune smoke..." >&2
bash scripts/dune_smoke.sh

echo "[overlay_lint] running wallet_graph smoke..." >&2
bash scripts/wallet_graph_smoke.sh
echo "[overlay_lint] running wallet_merge smoke..." >&2
bash scripts/wallet_merge_smoke.sh
echo "[overlay_lint] running hazard smoke..." >&2
bash scripts/hazard_smoke.sh

echo "[overlay_lint] running coordination smoke..." >&2
bash scripts/coordination_smoke.sh

echo "[overlay_lint] running jupiter quote smoke..." >&2
bash scripts/jupiter_quote_smoke.sh
echo "[overlay_lint] running orca_whirlpools smoke..." >\&2
bash scripts/orca_whirlpools_smoke.sh
echo "[overlay_lint] running raydium_pool smoke..." >&2
bash scripts/raydium_pool_smoke.sh

echo "[overlay_lint] running raydium_dex smoke..." >&2
bash scripts/raydium_dex_smoke.sh

echo "[overlay_lint] running solanafm smoke..." >&2
bash scripts/solanafm_smoke.sh

echo "[overlay_lint] running meteora_dlmm smoke..." >&2
bash scripts/meteora_dlmm_smoke.sh

echo "[overlay_lint] running wallet_behavior smoke..." >&2
bash scripts/wallet_behavior_smoke.sh

echo "[overlay_lint] running hazard_model smoke..." >&2
bash scripts/hazard_model_smoke.sh

echo "[overlay_lint] running position_sizing smoke..." >&2
bash scripts/position_sizing_smoke.sh

echo "[overlay_lint] running memecoin_features smoke..." >&2
bash scripts/memecoin_features_smoke.sh

echo "[overlay_lint] running token_mapping smoke..." >&2
bash scripts/token_mapping_smoke.sh

echo -e "${GREEN}[overlay_lint] ALL CHECKS PASSED${NC}" >&2
echo "[overlay_lint] running risk regime smoke..." >&2
bash scripts/risk_regime_smoke.sh

echo "[overlay_lint] running event_risk smoke..." >&2
bash scripts/event_risk_smoke.sh

echo "[overlay_lint] running regime_integration smoke..." >&2
bash scripts/regime_integration_smoke.sh

echo -e "${GREEN}[overlay_lint] ALL CHECKS PASSED${NC}" >&2
