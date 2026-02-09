# Sprints

This repo follows "rails-first": every slice of strategy work lands behind deterministic smokes and stable contracts.

## Sprint-1: Data layers → features → dataset (miniML-ready)

Goal: make the **dataset loop** real and deterministic: `trades_norm + (token_snapshots, wallet_profiles) → features → labels → training dataset`.

### PR-1: token_snapshots
- Implement / harden `integration/token_snapshot_store.py` and its fixture.
- Wire snapshots into gates (when available) and into feature builder/dataset export.
- Keep rails smoke stable.

### PR-2: wallet_profiles
- Implement / harden `integration/wallet_profile_store.py` and its fixture.
- Wire wallet profiles into gates (when available) and into feature builder/dataset export.
- Keep rails smoke stable.

### PR-3: dataset_enrichment + coverage
- Ensure exported dataset features are **meaningful** (not all zeros).
- Add a small coverage report (snapshot/profile presence; non-null/non-zero rates for key `f_*`).
- Extend `scripts/features_smoke.sh` if needed.

### PR-4: labels (y_*)
- Add deterministic labels in `tools/export_training_dataset.py` computed from future trades of the same mint within a horizon.
- Extend `scripts/features_smoke.sh` to validate label columns.


## Sprint-2 (Risk → sim → +EV)

### PR-C: risk_engine_v1

#### Goal
Implement risk engine v1 and kill-switch logic, then move to sim/+EV evaluation.


## Sprint-3 (Variant A: tunable config + mode observability)

Variant A focus: **make strategy tuning measurable and safe** (config guardrails + per-mode metrics) without rewriting core logic.

### PR-4A.1: config validator + config_smoke (DONE)

#### Goal
Fail fast on invalid strategy YAML (ttl=0, TP/SL sign errors, hold ordering, etc.) **before** running the pipeline.

#### Files (1:1)
- `integration/validate_strategy_config.py`
- `scripts/config_smoke.sh`
- `scripts/paper_runner_smoke.sh` (calls config_smoke early; stdout-contract unchanged)

#### DoD
- `bash scripts/config_smoke.sh`
- `bash scripts/paper_runner_smoke.sh` stays green (stdout guard unchanged)

### PR-4A.2: negative fixtures + config_negative_smoke (DONE)

#### Goal
Add "negative coverage" for the validator: known-bad YAML fixtures must fail deterministically with greppable `ERROR:` lines.

#### Files (1:1)
- `integration/fixtures/config/bad_ttl_sec.yaml`
- `integration/fixtures/config/bad_tp_pct.yaml`
- `integration/fixtures/config/bad_sl_pct.yaml`
- `integration/fixtures/config/bad_hold_sec_order.yaml`
- `scripts/config_negative_smoke.sh`

#### DoD
- `bash scripts/config_negative_smoke.sh`
- Stdout remains empty on success.

### PR-4A.3: mode registry + metrics-by-mode (DONE)

#### Goal
Normalize "modes" from config into a single runtime registry and emit **per-mode counters** in `paper_pipeline --summary-json`.

#### Files (1:1)
- `integration/mode_registry.py` (new)
- `integration/paper_pipeline.py` (add `mode_counts` to summary)
- `integration/validate_strategy_config.py` (optional: validate resolved mode profiles; non-breaking)
- `integration/fixtures/config/modes_two_profiles.yaml` (new)
- `integration/fixtures/trades.modes_two_profiles.jsonl` (new)
- `integration/fixtures/expected_modes_two_profiles.json` (new)
- `scripts/modes_smoke.sh` (new)
- `scripts/overlay_lint.sh` (call `bash scripts/modes_smoke.sh`)

#### Hard rules
- Stdout contract: with `--summary-json`, stdout is **exactly 1 JSON line**.
- Do **not** change `integration/fixtures/expected_counts.json`.

#### DoD
- `bash scripts/config_smoke.sh`
- `bash scripts/config_negative_smoke.sh`
- `bash scripts/modes_smoke.sh`
- `bash scripts/overlay_lint.sh`
- `bash scripts/paper_runner_smoke.sh`
- `bash scripts/features_smoke.sh`

See also: `strategy/docs/overlay/PR_MODES.md` (full agent task for PR-4A.3).

### PR-4A.4: mode edgecases (unknown + no-mode fallback) (DONE)

#### Goal
Lock down the **mode bucketing** contract for two critical edgecases:

- Trade has `mode` but it is **not** in the registry → bucket `__unknown_mode__`
- Trade has **no** `mode` → fallback to `U` if present, else the first mode in
  `sorted(resolved_modes)`

#### Files (1:1)
- `integration/fixtures/trades.modes_unknown.jsonl` (new)
- `integration/fixtures/trades.modes_nomode.jsonl` (new)
- `integration/fixtures/expected_modes_unknown.json` (new)
- `integration/fixtures/expected_modes_nomode.json` (new)
- `scripts/modes_smoke.sh` (extended with 2 extra cases)

#### Hard rules
- Stdout contract: with `--summary-json`, stdout is **exactly 1 JSON line**.
- No new dependencies.

#### DoD
- `bash scripts/modes_smoke.sh`
- `bash scripts/overlay_lint.sh`

### PR-4A.5: modes tuning playbook (DONE)

#### Goal
Document a deterministic tuning workflow for modes (U/S/M/L or custom),
including a template for recording results and guardrails to avoid accidental
config drift.

#### DoD
- A short doc under `strategy/docs/overlay/` describing the tuning loop and a
  results template.

## Sprint-4B (Wallet tiers + results registry)

### PR-4B.1: wallet tiers registry + tier_counts (DONE)

### PR-4B.2: strategy results template + docs coverage hook (DONE)

#### Goal
Provide a diff-friendly results template and a small docs smoke so it never regresses.

#### Files (1:1)
- `strategy/docs/overlay/RESULTS_TEMPLATE.md`
- `strategy/docs/overlay/results/results_v1.json`
- `scripts/docs_smoke.sh`

#### DoD
- `bash scripts/docs_smoke.sh` stays green
- `bash scripts/overlay_lint.sh` stays green

## Sprint-5 (Sim preflight)

### PR-5: sim preflight + +EV gate + PnL metrics (NEXT)

#### Goal
Add a deterministic offline **sim preflight** layer that produces `sim_metrics` in the
single-line `paper_pipeline --summary-json` output (stdout contract preserved).

#### Notes
- Use fixtures only (no external calls, no randomness).
- Gate decisions with a simple +EV rule (skip reasons include `ev_below_threshold`).

#### DoD
- New smoke (`scripts/sim_preflight_smoke.sh`) wired into `scripts/overlay_lint.sh`.

### PR-7: daily_metrics.v1 aggregation (DONE)

#### Goal
Add deterministic PnL aggregation into daily metrics. The `daily_metrics.v1` schema provides comprehensive breakdown of trading performance including PnL, ROI, winrate, max drawdown, and fill rate with breakdowns by mode and tier.

#### Files (1:1)
- `integration/pnl_aggregator.py` (new)
- `integration/fixtures/trades.daily_metrics.jsonl` (new)
- `integration/fixtures/config/daily_metrics.yaml` (new)
- `scripts/daily_metrics_smoke.sh` (new)
- `scripts/daily_metrics_negative_smoke.sh` (new)
- `strategy/docs/overlay/PR_DAILY_METRICS.md` (new)
- `integration/paper_pipeline.py` (add `--daily-metrics` flag)
- `scripts/overlay_lint.sh` (add daily_metrics smoke calls)
- `scripts/docs_smoke.sh` (add PR_DAILY_METRICS.md grep checks)

#### Hard rules
- `--daily-metrics` requires `--sim-preflight` (soft error with RC=2)
- Stdout contract preserved: exactly 1 JSON line with `--summary-json`
- All computation offline, deterministic

#### DoD
- `bash scripts/daily_metrics_smoke.sh`
- `bash scripts/daily_metrics_negative_smoke.sh`
- `bash scripts/overlay_lint.sh`
