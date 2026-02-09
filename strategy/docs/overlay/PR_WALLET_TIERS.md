# PR-4B.1: Wallet tiers registry + tier_counts

This PR adds a deterministic wallet tiering layer that converts wallet profile metrics
into a stable tier label, and then reports per-tier breakdown counters in
`paper_pipeline --summary-json` under `tier_counts`.

## Deterministic tiering rules

Tiering is computed from wallet profile metrics (e.g. `roi_30d_pct`, `winrate_30d`,
`trades_30d`) using fixed thresholds (with optional overrides from strategy config).

* If required metrics are missing → `tier3`.
* Otherwise, tiers are chosen deterministically by comparing the metrics to the
  threshold table.

## Summary metrics

`paper_pipeline --summary-json` emits:

* `tier_counts.<tier>.*` — mirrors the global pipeline counters, bucketed by tier.
* Special bucket: `__missing_wallet_profile__` for lines where a wallet profile is
  not available.

## Guardrails

Always keep the rails green:

* `bash scripts/tiers_smoke.sh`
* `bash scripts/overlay_lint.sh`

And ensure existing smokes remain green (modes/config/features/paper runner).