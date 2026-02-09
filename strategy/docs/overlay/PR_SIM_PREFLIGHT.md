# PR-5: Sim preflight (offline) + +EV gate + PnL metrics

This PR adds a deterministic, offline **sim preflight** layer that turns:

`signals → ENTER/SKIP decisions → simulated exits (TP/SL/TIME) → PnL aggregates`

Hard rule: **stdout contracts must not change**. Anything beyond the single `--summary-json` line goes to **stderr**.

## Deterministic preflight

Preflight must be reproducible from fixtures: no time-based logic, no randomness, no external calls.

## What this adds

### sim_metrics.v1

`paper_pipeline --summary-json` will gain a new optional key:

* `sim_metrics` (schema: `sim_metrics.v1`)

It must not break existing consumers of `counts`, `mode_counts`, or `tier_counts`.

## +EV gate

Signals are turned into **ENTER** or **SKIP** using a deterministic +EV rule (no ML).

* If token snapshot is missing → `SKIP` with reason `missing_snapshot`
* If wallet profile is missing → `SKIP` with reason `missing_wallet_profile`
* Otherwise compute `edge_bps` from snapshot features and costs
  * If `edge_bps < min_edge_bps` → `SKIP` with reason `ev_below_threshold`
  * Else → `ENTER`

Required reason token (must stay stable): `ev_below_threshold`.

## Simulation model

Minimal deterministic simulation:

* Future ticks come from the same `trades.jsonl` for the same `mint`, with `ts > entry_ts`, sorted by timestamp.
* Exit conditions:
  * **TP**: `price >= entry_price * (1 + tp_pct)`
  * **SL**: `price <= entry_price * (1 + sl_pct)` (sl_pct is negative)
  * **TIME**: when `hold_sec_max` elapses

Aggregate metrics must include totals and breakdowns:

* totals: positions_total, positions_closed, winrate, roi_total, avg_pnl_usd
* exit_reason_counts: TP / SL / TIME
* by_mode (if `Trade.extra["mode"]` exists)
* by_tier (if `Trade.extra["wallet_tier"]` exists)

## Fixtures & smoke

Add a deterministic smoke (`scripts/sim_preflight_smoke.sh`) that:

* runs preflight on dedicated fixtures
* asserts stdout is exactly **one** JSON line
* asserts `sim_metrics.schema_version == "sim_metrics.v1"`
* asserts two positions are closed: 1 TP and 1 SL
* ends stderr with: `[sim_preflight] OK ✅`

## Wiring

`scripts/overlay_lint.sh` must call `bash scripts/sim_preflight_smoke.sh` before the final success message.
