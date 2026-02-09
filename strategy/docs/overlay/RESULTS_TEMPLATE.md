# RESULTS_TEMPLATE.v1

A **diff-friendly** template to record strategy tuning runs in a repeatable and auditable way.

Use this file (or a copied version) as the canonical place to capture:
- what you changed (config + thresholds),
- what fixtures you ran,
- what the deterministic summary JSON reported (counts + breakdowns),
- and what decision you made next.

## Modes summary

Capture the relevant `mode_counts` fields from `paper_pipeline --summary-json`.

Suggested paste:
- `counts.total_lines`, `counts.passed`, `counts.rejected_by_gates`, `counts.filtered_out`
- `mode_counts.<MODE>.total_lines`
- `mode_counts.<MODE>.passed`
- `mode_counts.<MODE>.rejected_by_gates`
- `mode_counts.<MODE>.filtered_out`

## Wallet tiers summary

Capture the relevant `tier_counts` fields from `paper_pipeline --summary-json`.

Suggested paste:
- `tier_counts.<tier>.total_lines`
- `tier_counts.<tier>.passed`
- `tier_counts.<tier>.rejected_by_gates`
- `tier_counts.<tier>.filtered_out`

## Decision log

A short, structured log of what changed and why.

- **Hypothesis:**
- **Change:** (config path + a short diff summary)
- **Expected effect:**
- **Observed effect:** (key deltas from summary)
- **Decision:** keep / revert / iterate

## Next parameter changes

List the exact next edits you plan to make (keep each line atomic).

- [ ]
- [ ]

---

### Copy-paste results row (suggested)

| date_utc | run_id | config_path | fixture | modes | total_lines | passed_total | passed_by_mode | rejected_by_gates_by_mode | tier_counts_summary | notes |
|---|---|---|---|---|---:|---:|---|---|---|---|
| 2026-01-12 | trace_0001 | strategy/config/params_exp.yaml | integration/fixtures/trades.sample.jsonl | U,S | 120 | 8 | U:5,S:3 | U:60,S:52 | tier1:2,tier3:118 | tighten slippage for S |
